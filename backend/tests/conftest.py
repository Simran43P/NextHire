"""
Shared fixtures.

The local model is mocked in every test. Nothing here contacts Ollama, RapidAPI,
or any other network service, so the suite runs offline, in under a second, and
spends no API quota.
"""

import pytest


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
