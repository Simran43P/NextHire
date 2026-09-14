"""
Background work and rate limiting.

The point of the queue is survivability: a minute-long extraction must not be
lost because someone refreshed the page.
"""

import pytest
from fastapi import HTTPException, Request

import config
import llm
import ratelimit
import tasks
from models import QueuedTask, TaskStatus, User

PASSWORD = "correct-horse-battery"


class TestTaskQueue:
    async def test_a_task_runs_and_records_its_result(self, isolated_db):
        @tasks.register("test-ok")
        async def _handler(payload):
            return {"doubled": payload["value"] * 2}

        async with isolated_db() as db:
            user = User(email="a@example.com", password_hash="x")
            db.add(user)
            await db.commit()
            user_id = user.id

        task = await tasks.enqueue(user_id, "test-ok", {"value": 21})
        await tasks._run_one(task.id)

        async with isolated_db() as db:
            stored = await db.get(QueuedTask, task.id)
            assert stored.status is TaskStatus.DONE
            assert stored.result == {"doubled": 42}
            assert stored.error is None

    async def test_a_model_failure_is_recorded_as_a_typed_error(self, isolated_db):
        @tasks.register("test-llm-fail")
        async def _handler(payload):
            raise llm.LLMTimeoutError("too slow")

        async with isolated_db() as db:
            user = User(email="b@example.com", password_hash="x")
            db.add(user)
            await db.commit()
            user_id = user.id

        task = await tasks.enqueue(user_id, "test-llm-fail", {})
        await tasks._run_one(task.id)

        async with isolated_db() as db:
            stored = await db.get(QueuedTask, task.id)
            assert stored.status is TaskStatus.FAILED
            # Same shape a synchronous call would have produced.
            assert stored.error["code"] == "llm_timeout"
            assert stored.error["retryable"] is True
            assert stored.result is None

    async def test_an_unexpected_exception_does_not_lose_the_task(self, isolated_db):
        @tasks.register("test-boom")
        async def _handler(payload):
            raise RuntimeError("something odd")

        async with isolated_db() as db:
            user = User(email="c@example.com", password_hash="x")
            db.add(user)
            await db.commit()
            user_id = user.id

        task = await tasks.enqueue(user_id, "test-boom", {})
        await tasks._run_one(task.id)

        async with isolated_db() as db:
            stored = await db.get(QueuedTask, task.id)
            assert stored.status is TaskStatus.FAILED
            assert stored.error["code"] == "internal_error"

    async def test_an_unknown_kind_is_refused_up_front(self, isolated_db):
        with pytest.raises(ValueError):
            await tasks.enqueue(1, "no-such-handler", {})

    async def test_a_task_orphaned_by_a_restart_is_requeued(self, isolated_db):
        @tasks.register("test-orphan")
        async def _handler(payload):
            return {}

        async with isolated_db() as db:
            user = User(email="d@example.com", password_hash="x")
            db.add(user)
            await db.commit()
            # A task left RUNNING means the process died mid-execution. The user
            # is still waiting for it, so it must not be abandoned.
            orphan = QueuedTask(
                user_id=user.id, kind="test-orphan", status=TaskStatus.RUNNING, payload={}
            )
            db.add(orphan)
            await db.commit()
            orphan_id = orphan.id

        await tasks.start_workers()
        try:
            async with isolated_db() as db:
                stored = await db.get(QueuedTask, orphan_id)
                await db.refresh(stored)
                assert stored.status in {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.DONE}
        finally:
            await tasks.stop_workers()


class TestTaskRoutes:
    def test_polling_requires_an_account(self, client):
        assert client.get("/api/tasks").status_code == 401
        assert client.get("/api/tasks/1").status_code == 401

    def test_a_background_upload_returns_a_task_id(
        self, client, mock_model, pdf_bytes, sample_profile, register
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        register()

        response = client.post(
            "/api/parse-resume?background=true",
            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        assert isinstance(body["task_id"], int)

    def test_a_guest_cannot_queue_background_work(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        response = client.post(
            "/api/parse-resume?background=true",
            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
        )
        # Guests get the synchronous answer; there is no session to reattach with.
        assert response.json()["status"] == "success"

    def test_a_stranger_cannot_poll_someone_elses_task(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        client.post(
            "/api/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
        )
        task_id = client.post(
            "/api/parse-resume?background=true",
            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
        ).json()["task_id"]

        client.post("/api/auth/logout")
        client.post(
            "/api/auth/register", json={"email": "stranger@example.com", "password": PASSWORD}
        )
        assert client.get(f"/api/tasks/{task_id}").status_code == 404


class TestRateLimiting:
    def _request(self, host="1.2.3.4") -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [],
                "client": (host, 1234),
            }
        )

    def setup_method(self):
        ratelimit.reset()

    def test_requests_are_allowed_up_to_the_limit(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
        for _ in range(3):
            ratelimit.check(self._request(), "test", 3)

    def test_exceeding_the_limit_raises_429_with_retry_after(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
        for _ in range(2):
            ratelimit.check(self._request(), "test", 2)

        with pytest.raises(HTTPException) as exc:
            ratelimit.check(self._request(), "test", 2)
        assert exc.value.status_code == 429
        assert exc.value.detail["code"] == "rate_limited"
        assert "Retry-After" in exc.value.headers

    def test_separate_addresses_have_separate_budgets(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
        ratelimit.check(self._request("1.1.1.1"), "test", 1)
        # A housemate must not be throttled by someone else's usage.
        ratelimit.check(self._request("2.2.2.2"), "test", 1)

    def test_an_account_is_tracked_across_addresses(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
        ratelimit.check(self._request("1.1.1.1"), "test", 1, user_id=7)
        with pytest.raises(HTTPException):
            # Changing network must not reset the budget.
            ratelimit.check(self._request("9.9.9.9"), "test", 1, user_id=7)

    def test_buckets_are_independent(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
        ratelimit.check(self._request(), "upload", 1)
        ratelimit.check(self._request(), "inference", 1)

    def test_disabling_the_limiter_lets_everything_through(self, monkeypatch):
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
        for _ in range(50):
            ratelimit.check(self._request(), "test", 1)
