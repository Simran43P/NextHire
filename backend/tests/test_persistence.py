"""
Persistence, ownership, and analysis caching.

The ownership tests matter most. Every one of them is a scenario where a bug
would mean one candidate reading another's resume - which, given what a resume
contains, is the worst thing this application could do.
"""

import config

PASSWORD = "correct-horse-battery"


def _register(client, email):
    response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return response.json()


def _upload(client, pdf_bytes):
    return client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
    ).json()


class TestProfilePersistence:
    def test_a_signed_in_upload_is_stored(self, client, mock_model, pdf_bytes, sample_profile):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "asha@example.com")

        body = _upload(client, pdf_bytes)
        assert body["profile_id"] is not None
        assert body["profile_version"] == 1

        listed = client.get("/api/profiles").json()["profiles"]
        assert len(listed) == 1
        assert listed[0]["name"] == "Asha Menon"

    def test_a_profile_survives_a_new_session(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "asha@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]

        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})

        assert client.get(f"/api/profiles/{profile_id}").status_code == 200

    def test_correcting_a_profile_bumps_its_version(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "asha@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]

        corrected = {**sample_profile, "name": "Asha M."}
        response = client.patch(
            f"/api/profiles/{profile_id}", json={"profile": corrected}
        )
        assert response.status_code == 200
        assert response.json()["profile_version"] == 2
        assert response.json()["profile"]["name"] == "Asha M."


class TestOwnership:
    """Nobody may reach another account's data, and must not learn it exists."""

    def _two_users_one_profile(self, client, mock_model, pdf_bytes, sample_profile):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "owner@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]

        client.post("/api/auth/logout")
        _register(client, "stranger@example.com")
        return profile_id

    def test_a_stranger_cannot_read_a_profile(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        profile_id = self._two_users_one_profile(client, mock_model, pdf_bytes, sample_profile)
        response = client.get(f"/api/profiles/{profile_id}")
        # 404, not 403: confirming the row exists is itself a disclosure.
        assert response.status_code == 404

    def test_a_stranger_cannot_edit_a_profile(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        profile_id = self._two_users_one_profile(client, mock_model, pdf_bytes, sample_profile)
        response = client.patch(f"/api/profiles/{profile_id}", json={"profile": {"name": "X"}})
        assert response.status_code == 404

    def test_a_stranger_cannot_download_the_pdf(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        profile_id = self._two_users_one_profile(client, mock_model, pdf_bytes, sample_profile)
        assert client.get(f"/api/profiles/{profile_id}/resume").status_code == 404

    def test_a_stranger_cannot_analyse_against_a_profile(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        profile_id = self._two_users_one_profile(client, mock_model, pdf_bytes, sample_profile)
        response = client.post(
            "/api/analyze-ats",
            json={"profile_id": profile_id, "job_description": "Python required."},
        )
        assert response.status_code == 404

    def test_a_guest_cannot_use_a_profile_id_at_all(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "owner@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]
        client.post("/api/auth/logout")

        assert client.get(f"/api/profiles/{profile_id}").status_code == 401
        assert (
            client.post("/api/infer-titles", json={"profile_id": profile_id}).status_code
            == 404
        )

    def test_listing_profiles_requires_an_account(self, client):
        assert client.get("/api/profiles").status_code == 401

    def test_the_owner_can_download_their_own_pdf(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "owner@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]

        response = client.get(f"/api/profiles/{profile_id}/resume")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")


class TestAnalysisCaching:
    def _setup(self, client, mock_model, pdf_bytes, sample_profile, monkeypatch):
        monkeypatch.setattr(config, "USE_MOCK_JOBS", True)
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "asha@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]

        jobs = client.post(
            "/api/jobs",
            json={"job_titles": [{"title": "Backend Engineer"}], "profile_id": profile_id},
        ).json()["jobs"]
        return profile_id, jobs[0]["job_id"]

    def test_stored_postings_carry_a_database_id(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        _, job_id = self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        # Without it the next stage has nothing to key a cache on.
        assert isinstance(job_id, int)

    def test_a_repeat_analysis_is_served_from_cache(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        profile_id, job_id = self._setup(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )

        calls = {"n": 0}

        async def _counting_analysis(resume_profile, job_description):
            calls["n"] += 1
            return {
                "match_score": 72,
                "matched_skills": ["Python"],
                "missing_skills": [],
                "recommendations": [],
                "evidence": {},
                "label": "Good Match",
                "summary": "Fine.",
                "corrected_skills": [],
            }

        monkeypatch.setattr("routers.pipeline.analyze_job_match", _counting_analysis)

        first = client.post("/api/analyze-ats", json={"profile_id": profile_id, "job_id": job_id})
        second = client.post("/api/analyze-ats", json={"profile_id": profile_id, "job_id": job_id})

        assert first.json()["analysis"]["match_score"] == 72
        assert second.json()["analysis"]["match_score"] == 72
        assert second.json()["analysis"]["cached"] is True
        # A 30-second inference must not run twice for the same question.
        assert calls["n"] == 1

    def test_correcting_the_profile_invalidates_the_cache(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        profile_id, job_id = self._setup(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )

        calls = {"n": 0}

        async def _counting_analysis(resume_profile, job_description):
            calls["n"] += 1
            return {
                "match_score": 50 + calls["n"],
                "matched_skills": [],
                "missing_skills": [],
                "recommendations": [],
                "evidence": {},
                "label": "Weak Match",
                "summary": "",
                "corrected_skills": [],
            }

        monkeypatch.setattr("routers.pipeline.analyze_job_match", _counting_analysis)

        client.post("/api/analyze-ats", json={"profile_id": profile_id, "job_id": job_id})
        client.patch(
            f"/api/profiles/{profile_id}",
            json={"profile": {**sample_profile, "skills": ["Python", "Docker"]}},
        )
        again = client.post("/api/analyze-ats", json={"profile_id": profile_id, "job_id": job_id})

        # The cache keys on profile version, so an edited profile re-scores
        # rather than silently showing the old number.
        assert calls["n"] == 2
        assert again.json()["analysis"]["match_score"] == 52

    def test_refresh_forces_a_rerun(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        profile_id, job_id = self._setup(
            client, mock_model, pdf_bytes, sample_profile, monkeypatch
        )
        calls = {"n": 0}

        async def _counting_analysis(resume_profile, job_description):
            calls["n"] += 1
            return {
                "match_score": 60,
                "matched_skills": [],
                "missing_skills": [],
                "recommendations": [],
                "evidence": {},
                "label": "Fair Match",
                "summary": "",
                "corrected_skills": [],
            }

        monkeypatch.setattr("routers.pipeline.analyze_job_match", _counting_analysis)
        client.post("/api/analyze-ats", json={"profile_id": profile_id, "job_id": job_id})
        client.post(
            "/api/analyze-ats?refresh=true",
            json={"profile_id": profile_id, "job_id": job_id},
        )
        assert calls["n"] == 2


class TestAccountData:
    def test_export_contains_the_stored_work(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "asha@example.com")
        _upload(client, pdf_bytes)

        export = client.get("/api/account/export").json()
        assert export["account"]["email"] == "asha@example.com"
        assert len(export["profiles"]) == 1
        assert export["profiles"][0]["data"]["name"] == "Asha Menon"
        assert len(export["resumes"]) == 1

    def test_export_requires_an_account(self, client):
        assert client.get("/api/account/export").status_code == 401

    def test_deleting_an_account_removes_everything(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        _register(client, "asha@example.com")
        profile_id = _upload(client, pdf_bytes)["profile_id"]

        response = client.post("/api/account/delete", json={"password": PASSWORD})
        assert response.status_code == 200

        # Access is revoked immediately, and signing back in is impossible.
        assert client.get("/api/auth/me").json()["user"] is None
        assert (
            client.post(
                "/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}
            ).status_code
            == 400
        )

        # Re-registering the same email yields a clean account, not the old data.
        _register(client, "asha@example.com")
        assert client.get("/api/profiles").json()["profiles"] == []
        assert client.get(f"/api/profiles/{profile_id}").status_code == 404

    def test_deletion_requires_the_password(self, client, register):
        register()
        response = client.post("/api/account/delete", json={"password": "not-my-password"})
        assert response.status_code == 400
        assert client.get("/api/auth/me").json()["user"] is not None
