"""
Background model work.

Extraction can take a minute on CPU. Holding an HTTP request open for that long
means a refresh, a flaky connection, or a closed laptop lid loses the work
entirely - and the user cannot tell a slow call from a hung one.

So model work is recorded as a row, run by an in-process worker, and polled by
the client. Refreshing the page mid-extraction now costs nothing: the task is
still running, and the client reattaches to it by id.

Deliberately not Celery or a broker. A single-process asyncio worker backed by a
database table needs no extra service, no extra cost, and survives the only
failure that actually happens here - the browser going away.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select

import config
import llm
from db import get_sessionmaker
from models import QueuedTask, TaskStatus, utcnow

# kind -> coroutine taking the payload and returning a JSON-serialisable result
Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

_handlers: dict[str, Handler] = {}
_workers: list[asyncio.Task] = []
_queue: asyncio.Queue[int] | None = None


def register(kind: str) -> Callable[[Handler], Handler]:
    def decorate(handler: Handler) -> Handler:
        _handlers[kind] = handler
        return handler

    return decorate


def _get_queue() -> asyncio.Queue[int]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue(user_id: int, kind: str, payload: dict[str, Any]) -> QueuedTask:
    """Record a task and hand it to the worker pool."""
    if kind not in _handlers:
        raise ValueError(f"no handler registered for task kind {kind!r}")

    async with get_sessionmaker()() as db:
        task = QueuedTask(user_id=user_id, kind=kind, payload=payload)
        db.add(task)
        await db.commit()
        await db.refresh(task)

    _get_queue().put_nowait(task.id)
    print(f"[tasks] queued {kind} as task {task.id} for user {user_id}")
    return task


async def _run_one(task_id: int) -> None:
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as db:
        task = await db.get(QueuedTask, task_id)
        if task is None or task.status is not TaskStatus.QUEUED:
            return
        task.status = TaskStatus.RUNNING
        await db.commit()
        kind, payload = task.kind, dict(task.payload or {})

    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    try:
        result = await _handlers[kind](payload)
    except llm.LLMError as exc:
        # A typed model failure is expected traffic, not an incident. It reaches
        # the client with the same shape a synchronous call would have given.
        error = {**exc.as_dict(), "stage": kind, "retryable": True}
        print(f"[tasks] task {task_id} ({kind}) failed: {exc.code}")
    except Exception as exc:
        print(f"[tasks] task {task_id} ({kind}) raised:")
        traceback.print_exc()
        error = {
            "code": "internal_error",
            "message": "Something went wrong on our side. Please try again.",
            "stage": kind,
            "retryable": True,
            "detail": str(exc),
        }

    async with sessionmaker() as db:
        task = await db.get(QueuedTask, task_id)
        if task is None:
            return
        task.status = TaskStatus.DONE if error is None else TaskStatus.FAILED
        task.result = result
        task.error = error
        task.finished_at = utcnow()
        await db.commit()

    print(f"[tasks] task {task_id} ({kind}) -> {'DONE' if error is None else 'FAILED'}")


async def _worker(index: int) -> None:
    queue = _get_queue()
    while True:
        task_id = await queue.get()
        try:
            await _run_one(task_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - the worker must never die
            print(f"[tasks] worker {index} recovered from an unexpected failure:")
            traceback.print_exc()
        finally:
            queue.task_done()


async def start_workers() -> None:
    """
    Start the worker pool and requeue anything left mid-flight.

    A task stuck in RUNNING means the process died while it was executing. It is
    reset to QUEUED rather than abandoned, because the user is still waiting for
    it on the other side.
    """
    if _workers:
        return

    async with get_sessionmaker()() as db:
        result = await db.execute(
            select(QueuedTask).where(QueuedTask.status == TaskStatus.RUNNING)
        )
        orphans = list(result.scalars())
        for task in orphans:
            task.status = TaskStatus.QUEUED
        if orphans:
            await db.commit()
            print(f"[tasks] requeued {len(orphans)} task(s) orphaned by a restart")

        result = await db.execute(
            select(QueuedTask.id).where(QueuedTask.status == TaskStatus.QUEUED)
        )
        pending = list(result.scalars())

    queue = _get_queue()
    for task_id in pending:
        queue.put_nowait(task_id)

    # Matched to the model's own concurrency limit: more workers than the model
    # will serve at once just moves the queue from here to there.
    count = max(1, config.LLM_CONCURRENCY)
    for index in range(count):
        _workers.append(asyncio.create_task(_worker(index)))
    print(f"[tasks] {count} worker(s) started, {len(pending)} task(s) pending")


async def stop_workers() -> None:
    for worker in _workers:
        worker.cancel()
    for worker in _workers:
        try:
            await worker
        except (asyncio.CancelledError, Exception):
            pass
    _workers.clear()


def serialise(task: QueuedTask) -> dict[str, Any]:
    """The shape the client polls."""
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status.value,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }
