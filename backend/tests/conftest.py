"""
Shared fixtures.

The local model is mocked in every test. Nothing here contacts Ollama, RapidAPI,
or any other network service, so the suite runs offline, in under a few seconds,
and spends no API quota.

Each test that touches the database gets its own file-backed SQLite database in
a temporary directory, so tests cannot see each other's rows and none of them
can reach the real `nexthire.db`.
"""

import pytest

import config
import db as database
import ratelimit
import tasks as task_queue


@pytest.fixture
def sample_profile() -> dict:
    """A realistic fresher profile: strong projects, no employment history."""
    return {
        "name": "Asha Menon",
        "email": "asha.menon@example.com",
        "phone": "+91 98765 43210",
        "location": "Kochi, Kerala",
        "skills": ["Python", "React", "SQL", "FastAPI", "Git", "C++"],
        "years_of_experience": 0,
        "education": [
            {"degree": "B.Tech Computer Science", "college": "CUSAT", "year": "2026"}
        ],
        "experience": [],
        "projects": [
            {
                "name": "Resume Ranker",
                "description": "Ranked resumes against postings",
                "technologies": ["Python", "scikit-learn", "Streamlit"],
                "github": "https://github.com/example/resume-ranker",
                "live_demo": "",
            }
        ],
        "certifications": ["AWS Cloud Practitioner"],
        "languages": ["English", "Malayalam"],
        "links": {
            "github": "https://github.com/example",
            "linkedin": "",
            "portfolio": "",
        },
    }


@pytest.fixture
def sample_job_description() -> str:
    return (
        "We are hiring a Backend Engineer. You will build services in Python using "
        "FastAPI and PostgreSQL. Strong SQL skills are required. Experience with "
        "Docker and Kubernetes is preferred. Familiarity with Git is expected. "
        "Knowledge of Kafka and distributed systems is a plus."
    )


@pytest.fixture
def fake_llm(monkeypatch):
    """
    Replace `generate_json` in a named module with one returning a canned payload.

    Each AI module imports the function by name, so the patch has to target the
    module that uses it rather than llm itself.

        fake_llm("extractor", {"name": "Asha"})
        fake_llm("ats_matcher", raises=llm.LLMTimeoutError("slow"))
    """

    def install(module: str, payload: dict | None = None, *, raises: Exception | None = None):
        calls: list[str] = []

        async def _fake(prompt, *, timeout, stage, options=None):
            calls.append(prompt)
            if raises is not None:
                raise raises
            return payload if payload is not None else {}

        monkeypatch.setattr(f"{module}.generate_json", _fake)
        return calls

    return install


@pytest.fixture
def pdf_bytes():
    """Build a real, text-bearing PDF in memory."""
    import pymupdf

    def build(text: str = "") -> bytes:
        body = text or (
            "Asha Menon\nasha.menon@example.com | +91 98765 43210 | Kochi, Kerala\n"
            "Skills: Python, React, SQL, FastAPI, Git\n"
            "Education: B.Tech Computer Science, CUSAT, 2026\n"
            "Projects: Resume Ranker - ranked resumes against job postings using "
            "Python and scikit-learn, deployed with Streamlit.\n"
            "Certifications: AWS Cloud Practitioner\n"
        )
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), body, fontsize=10)
        data = document.tobytes()
        document.close()
        return data

    return build


# ---------------------------------------------------------------------------
# Database and application
# ---------------------------------------------------------------------------


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """A private database and storage directory for one test."""
    monkeypatch.setattr(
        config, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setattr(config, "STORAGE_DIR", str(tmp_path / "storage"))

    # The engine is cached in module globals; clear it so the new URL is used.
    await database.dispose()
    await database.create_all()
    ratelimit.reset()

    yield database.get_sessionmaker()

    await database.dispose()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    A TestClient wired to a private database.

    The app's lifespan runs, which creates the schema and starts the task
    workers, so this exercises the real startup path rather than a stand-in.
    """
    import asyncio

    from fastapi.testclient import TestClient

    import main

    monkeypatch.setattr(
        config, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setattr(config, "STORAGE_DIR", str(tmp_path / "storage"))
    ratelimit.reset()

    # Reset cached engine and worker state left over from a previous test.
    asyncio.run(database.dispose())
    task_queue._workers.clear()
    task_queue._queue = None

    with TestClient(main.app) as test_client:
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def register(client):
    """Register a user and return the response body. The client keeps the cookie."""

    def _register(email: str = "asha@example.com", password: str = "correct-horse-battery", **extra):
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, **extra},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _register


@pytest.fixture
def mock_model(monkeypatch):
    """Patch the AI entry points the pipeline router calls."""

    def install(*, extract=None, titles=None, analysis=None, raises=None):
        async def _extract(text):
            if raises:
                raise raises
            return extract or {"profile": {}, "gaps": []}

        async def _titles(profile):
            if raises:
                raise raises
            return titles or []

        async def _analysis(resume_profile, job_description):
            if raises:
                raise raises
            return analysis or {
                "match_score": 70,
                "matched_skills": ["Python"],
                "missing_skills": ["Docker"],
                "recommendations": ["Add container experience"],
                "evidence": {"Python": "Python required."},
                "label": "Good Match",
                "summary": "A good fit.",
                "corrected_skills": [],
            }

        monkeypatch.setattr("routers.pipeline.extract_resume_data", _extract)
        monkeypatch.setattr("routers.pipeline.infer_job_titles", _titles)
        monkeypatch.setattr("routers.pipeline.analyze_job_match", _analysis)

    return install
