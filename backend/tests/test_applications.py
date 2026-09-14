"""
The application tracker.

Mostly ordinary CRUD, with two behaviours worth pinning down: the applied date
is set by the first move out of SAVED rather than by hand, and the response
rate counts only applications that were actually sent.
"""

import config

PASSWORD = "correct-horse-battery"


def _register(client, email="asha@example.com"):
    response = client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201


def _job(client, mock_model, pdf_bytes, sample_profile, monkeypatch):
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
    return profile_id, jobs


class TestTracking:
    def test_a_posting_can_be_tracked(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        _register(client)
        _, jobs = _job(client, mock_model, pdf_bytes, sample_profile, monkeypatch)

        response = client.post("/api/applications", json={"job_id": jobs[0]["job_id"]})
        assert response.status_code == 201
        application = response.json()["application"]
        assert application["status"] == "SAVED"
        assert application["title"] == jobs[0]["title"]
        assert response.json()["already_tracked"] is False

    def test_tracking_the_same_job_twice_does_not_duplicate(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        _register(client)
        _, jobs = _job(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        job_id = jobs[0]["job_id"]

        first = client.post("/api/applications", json={"job_id": job_id}).json()
        second = client.post("/api/applications", json={"job_id": job_id}).json()

        # Clicking save twice is a slip, not an instruction.
        assert second["already_tracked"] is True
        assert second["application"]["id"] == first["application"]["id"]
        assert len(client.get("/api/applications").json()["columns"]["SAVED"]) == 1

    def test_tracking_needs_an_account(self, client):
        assert client.post("/api/applications", json={"job_id": 1}).status_code == 401

    def test_a_stranger_cannot_track_someone_elses_posting(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        _register(client, "owner@example.com")
        _, jobs = _job(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        job_id = jobs[0]["job_id"]

        client.post("/api/auth/logout")
        _register(client, "stranger@example.com")

        assert client.post("/api/applications", json={"job_id": job_id}).status_code == 404


class TestBoard:
    def _tracked(self, client, mock_model, pdf_bytes, sample_profile, monkeypatch, count=3):
        _register(client)
        _, jobs = _job(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        return [
            client.post("/api/applications", json={"job_id": job["job_id"]}).json()[
                "application"
            ]
            for job in jobs[:count]
        ]

    def test_applications_are_grouped_into_columns(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        self._tracked(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        body = client.get("/api/applications").json()

        assert body["order"] == ["SAVED", "APPLIED", "INTERVIEWING", "OFFER", "REJECTED"]
        assert len(body["columns"]["SAVED"]) == 3
        assert body["columns"]["APPLIED"] == []

    def test_moving_out_of_saved_stamps_the_applied_date(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        tracked = self._tracked(client, mock_model, pdf_bytes, sample_profile, monkeypatch, 1)
        assert tracked[0]["applied_at"] is None

        moved = client.patch(
            f"/api/applications/{tracked[0]['id']}", json={"status": "APPLIED"}
        ).json()["application"]
        # The date every follow-up question hangs off, set without asking.
        assert moved["applied_at"] is not None

    def test_moving_back_to_saved_clears_the_applied_date(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        tracked = self._tracked(client, mock_model, pdf_bytes, sample_profile, monkeypatch, 1)
        client.patch(f"/api/applications/{tracked[0]['id']}", json={"status": "APPLIED"})
        back = client.patch(
            f"/api/applications/{tracked[0]['id']}", json={"status": "SAVED"}
        ).json()["application"]
        assert back["applied_at"] is None

    def test_notes_and_follow_up_dates_persist(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        tracked = self._tracked(client, mock_model, pdf_bytes, sample_profile, monkeypatch, 1)
        updated = client.patch(
            f"/api/applications/{tracked[0]['id']}",
            json={"notes": "Referred by Priya", "follow_up_on": "2026-10-01T09:00:00Z"},
        ).json()["application"]

        assert updated["notes"] == "Referred by Priya"
        assert updated["follow_up_on"].startswith("2026-10-01")

    def test_an_application_can_be_untracked(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        tracked = self._tracked(client, mock_model, pdf_bytes, sample_profile, monkeypatch, 1)
        assert client.delete(f"/api/applications/{tracked[0]['id']}").status_code == 200
        assert client.get("/api/applications").json()["stats"]["total"] == 0

    def test_a_stranger_can_neither_see_nor_change_it(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        tracked = self._tracked(client, mock_model, pdf_bytes, sample_profile, monkeypatch, 1)
        application_id = tracked[0]["id"]

        client.post("/api/auth/logout")
        _register(client, "stranger@example.com")

        assert client.get("/api/applications").json()["stats"]["total"] == 0
        assert client.patch(
            f"/api/applications/{application_id}", json={"status": "OFFER"}
        ).status_code == 404
        assert client.delete(f"/api/applications/{application_id}").status_code == 404


class TestStats:
    def _setup(self, client, mock_model, pdf_bytes, sample_profile, monkeypatch):
        _register(client)
        _, jobs = _job(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        return [
            client.post("/api/applications", json={"job_id": job["job_id"]}).json()[
                "application"
            ]["id"]
            for job in jobs[:5]
        ]

    def test_saved_only_means_no_response_rate_yet(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        stats = client.get("/api/applications").json()["stats"]
        # Nothing has been sent, so there is nothing to have a rate of.
        assert stats["response_rate"] is None
        assert stats["awaiting_response"] == 0

    def test_the_response_rate_ignores_untouched_saved_rows(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        ids = self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        client.patch(f"/api/applications/{ids[0]}", json={"status": "APPLIED"})
        client.patch(f"/api/applications/{ids[1]}", json={"status": "INTERVIEWING"})

        stats = client.get("/api/applications").json()["stats"]
        # Two sent, one answered. Counting the three shortlisted-but-unsent rows
        # would make a careful shortlist look like rejection.
        assert stats["response_rate"] == 50
        assert stats["awaiting_response"] == 1

    def test_rejections_count_as_responses(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        ids = self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        client.patch(f"/api/applications/{ids[0]}", json={"status": "REJECTED"})
        assert client.get("/api/applications").json()["stats"]["response_rate"] == 100

    def test_applications_sent_this_week_are_counted(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        ids = self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        client.patch(f"/api/applications/{ids[0]}", json={"status": "APPLIED"})
        client.patch(f"/api/applications/{ids[1]}", json={"status": "APPLIED"})
        assert client.get("/api/applications").json()["stats"]["applied_this_week"] == 2

    def test_an_overdue_follow_up_is_surfaced(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        ids = self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        client.patch(f"/api/applications/{ids[0]}", json={"status": "APPLIED"})
        client.patch(
            f"/api/applications/{ids[0]}", json={"follow_up_on": "2020-01-01T09:00:00Z"}
        )
        assert client.get("/api/applications").json()["stats"]["follow_ups_due"] == 1

    def test_counts_are_reported_per_column(
        self, client, mock_model, pdf_bytes, sample_profile, monkeypatch
    ):
        ids = self._setup(client, mock_model, pdf_bytes, sample_profile, monkeypatch)
        client.patch(f"/api/applications/{ids[0]}", json={"status": "OFFER"})
        counts = client.get("/api/applications").json()["stats"]["counts"]
        assert counts["OFFER"] == 1
        assert counts["SAVED"] == 4
