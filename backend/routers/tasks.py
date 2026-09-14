"""
Polling for background work.

The client submits a long operation, gets a task id, and asks about it here.
That is what lets someone refresh the page mid-extraction, or close the laptop
and come back, without losing a minute of model time.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import tasks as task_queue
from db import get_db
from models import QueuedTask, TaskStatus, User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_active(
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Anything still in flight for this user.

    The client calls this on load: if a task is running from before a refresh,
    it reattaches instead of starting again.
    """
    result = await db.execute(
        select(QueuedTask)
        .where(
            QueuedTask.user_id == user.id,
            QueuedTask.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
        )
        .order_by(QueuedTask.created_at.desc())
    )
    return {
        "status": "success",
        "tasks": [task_queue.serialise(task) for task in result.scalars()],
    }


@router.get("/{task_id}")
async def get_task(
    task_id: int,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(QueuedTask, task_id)
    # Ownership checked before anything is revealed - including whether the
    # task exists at all.
    if task is None or task.user_id != user.id:
        raise auth.forbidden()
    return {"status": "success", "task": task_queue.serialise(task)}
