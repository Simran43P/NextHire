"""
The optimisation endpoints end to end.

Guests get proposals and a PDF but nothing is stored; signed-in users get the
tailored resume persisted with its before and after scores, and nobody can
reach anybody else's.
"""

import pytest

import config

PASSWORD = "correct-horse-battery"


@pytest.fixture
def mock_optimise(monkeypatch):
    """Stand in for the two model calls the optimisation flow makes."""

    def install(*, proposals=None, after_score=80, raises=None):
        async def _propose(profile, job_description, analysis):
            if raises:
                raise raises
            return proposals or {
                "changes": [
                    {
                        "id": "c0",
                        "kind": "summary",
                        "path": "summary",
                        "before": "",
                        "after": "Backend engineer with Python and SQL.",
                        "why": "positioned at this role",
                    }
                ],
                "rejected": [],
            }

        async def _analyse(resume_profile, job_description):
            return {
                "match_score": after_score,
                "matched_skills": ["Python"],
                "missing_skills": [],
                "recommendations": [],
                "evidence": {},
                "label": "Good Match",
                "summary": "Fine.",
                "corrected_skills": [],
            }

        monkeypatch.setattr("routers.optimize.optimizer.propose_optimisations", _propose)
        monkeypatch.setattr("routers.optimize.analyze_job_match", _analyse)

    return install


def _register(client, email="asha@example.com"):
    response = client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201
    return response.json()


def _pipeline(client, mock_model, pdf_bytes, sample_profile, monkeypatch):
    """Get a signed-in user to the point of having a profile and a posting."""
    monkeypatch.setattr(config, "USE_MOCK_JOBS", True)
    mock_model(extract={"profile": sample_profile, "gaps": []})
    profile_id = client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
    ).json()["profile_id"]
    jobs = client.post(
        "/api/jobs",
        json={"job_titles": [{"title": "Backend Engineer"}], "profile_id": profile_id},
    ).json()["jobs"]
    return profile_id, jobs[0]["job_id"]


class TestPropose:
    def test_a_guest_can_get_proposals_inline(
        self, client, mock_optimise, sample_profile, sample_job_description
    ):
        mock_optimise()
        response = client.post(
            "/api/optimize",
            json={
                "profile": sample_profile,
                "job_description": sample_job_description,
                "analysis": {"matched_skills": ["Python"], "missing_skills": []},
            },
        )
        assert response.status_code == 200
        assert response.json()["changes"][0]["id"] == "c0"

    def test_rejected_suggestions_are_reported_not_hidden(
        self, client, mock_optimise, sample_profile, sample_job_description
    ):
        mock_optimise(
            proposals={
                "changes": [],
                "rejected": [
                    {"id": "x", "after": "Ran Kubernetes", "fabricated": ["Kubernetes"]}
                ],
            }
        )
        body = client.post(
            "/api/optimize",
            json={"profile": sample_profile, "job_description": sample_job_description},
        ).json()
        assert body["rejected"][0]["fabricated"] == ["Kubernetes"]

    def test_a_missing_profile_is_rejected(self, client, mock_optimise):
        mock_optimise()
        response = client.post("/api/optimize", json={"job_description": "Python needed"})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_profile"

    def test_a_posting_with_no_description_is_rejected(
        self, client, mock_optimise, sample_profile
    ):
        mock_optimise()
        response = client.post(
            "/api/optimize", json={"profile": sample_profile, "job_description": "  "}
        )
        assert response.status_code == 400

    def test_a_stranger_cannot_optimise_against_someone_elses_profile(
        self, client, mock_model, mock_optimise, pdf_bytes, sample_profile, monkeypatch
    ):
        mock_optimise()
        _register(client, "owner@example.com")
        profile_id, job_id = _pipeline(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )

        client.post("/api/auth/logout")
        _register(client, "stranger@example.com")

        response = client.post(
            "/api/optimize", json={"profile_id": profile_id, "job_id": job_id}
        )
        assert response.status_code == 404


class TestApply:
    def test_applying_stores_the_result_with_both_scores(
        self, client, mock_model, mock_optimise, pdf_bytes, sample_profile, monkeypatch
    ):
        mock_optimise(after_score=88)
        _register(client)
        profile_id, job_id = _pipeline(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )

        changes = client.post(
            "/api/optimize", json={"profile_id": profile_id, "job_id": job_id}
        ).json()["changes"]

        response = client.post(
            "/api/optimize/apply",
            json={
                "profile_id": profile_id,
                "job_id": job_id,
                "changes": changes,
                "accepted_ids": ["c0"],
                "before_score": 70,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["before_score"] == 70
        assert body["after_score"] == 88
        assert body["tailored_profile"]["summary"].startswith("Backend engineer")
        assert isinstance(body["tailored_resume_id"], int)

    def test_accepting_nothing_is_refused(
        self, client, mock_optimise, sample_profile, sample_job_description
    ):
        mock_optimise()
        response = client.post(
            "/api/optimize/apply",
            json={
                "profile": sample_profile,
                "job_description": sample_job_description,
                "changes": [],
                "accepted_ids": [],
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "no_changes_accepted"

    def test_a_guest_gets_a_tailored_profile_but_nothing_is_stored(
        self, client, mock_optimise, sample_profile, sample_job_description
    ):
        mock_optimise()
        changes = client.post(
            "/api/optimize",
            json={"profile": sample_profile, "job_description": sample_job_description},
        ).json()["changes"]

        body = client.post(
            "/api/optimize/apply",
            json={
                "profile": sample_profile,
                "job_description": sample_job_description,
                "changes": changes,
                "accepted_ids": ["c0"],
            },
        ).json()
        assert body["tailored_profile"]["summary"]
        assert body["tailored_resume_id"] is None


class TestPdf:
    def test_a_guest_can_render_a_pdf(self, client, sample_profile):
        response = client.post("/api/optimize/pdf", json={"profile": sample_profile})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")

    def test_the_filename_is_derived_from_the_name(self, client, sample_profile):
        response = client.post("/api/optimize/pdf", json={"profile": sample_profile})
        assert "Asha-Menon-tailored.pdf" in response.headers["content-disposition"]

    def test_a_stored_tailored_resume_can_be_downloaded(
        self, client, mock_model, mock_optimise, pdf_bytes, sample_profile, monkeypatch
    ):
        mock_optimise()
        _register(client)
        profile_id, job_id = _pipeline(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )
        changes = client.post(
            "/api/optimize", json={"profile_id": profile_id, "job_id": job_id}
        ).json()["changes"]
        tailored_id = client.post(
            "/api/optimize/apply",
            json={
                "profile_id": profile_id,
                "job_id": job_id,
                "changes": changes,
                "accepted_ids": ["c0"],
            },
        ).json()["tailored_resume_id"]

        response = client.get(f"/api/tailored-resumes/{tailored_id}/pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")

    def test_a_stranger_cannot_download_it(
        self, client, mock_model, mock_optimise, pdf_bytes, sample_profile, monkeypatch
    ):
        mock_optimise()
        _register(client, "owner@example.com")
        profile_id, job_id = _pipeline(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )
        changes = client.post(
            "/api/optimize", json={"profile_id": profile_id, "job_id": job_id}
        ).json()["changes"]
        tailored_id = client.post(
            "/api/optimize/apply",
            json={
                "profile_id": profile_id,
                "job_id": job_id,
                "changes": changes,
                "accepted_ids": ["c0"],
            },
        ).json()["tailored_resume_id"]

        client.post("/api/auth/logout")
        _register(client, "stranger@example.com")

        assert client.get(f"/api/tailored-resumes/{tailored_id}").status_code == 404
        assert client.get(f"/api/tailored-resumes/{tailored_id}/pdf").status_code == 404


class TestListing:
    def test_listing_requires_an_account(self, client):
        assert client.get("/api/tailored-resumes").status_code == 401

    def test_only_your_own_are_listed(
        self, client, mock_model, mock_optimise, pdf_bytes, sample_profile, monkeypatch
    ):
        mock_optimise()
        _register(client, "owner@example.com")
        profile_id, job_id = _pipeline(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )
        changes = client.post(
            "/api/optimize", json={"profile_id": profile_id, "job_id": job_id}
        ).json()["changes"]
        client.post(
            "/api/optimize/apply",
            json={
                "profile_id": profile_id,
                "job_id": job_id,
                "changes": changes,
                "accepted_ids": ["c0"],
            },
        )
        assert len(client.get("/api/tailored-resumes").json()["tailored_resumes"]) == 1

        client.post("/api/auth/logout")
        _register(client, "stranger@example.com")
        assert client.get("/api/tailored-resumes").json()["tailored_resumes"] == []
