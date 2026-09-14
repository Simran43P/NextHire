"""
Route contracts for the pipeline, with the model mocked throughout.

These cover the guarantee the frontend is built on: a failure arrives as an HTTP
error carrying a machine-readable code, and a success always carries a complete,
correctly shaped payload.
"""

import pytest

import config
import llm


class TestHealth:
    def test_root_reports_mode(self, client):
        body = client.get("/").json()
        assert body["jobs_mode"] in {"mock", "live"}

    def test_health_reports_the_upload_limit_and_database(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["max_upload_mb"] == config.MAX_UPLOAD_MB
        assert body["database"] == "ok"


class TestParseResume:
    def test_a_valid_pdf_returns_a_profile(self, client, mock_model, pdf_bytes, sample_profile):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["profile"]["name"] == "Asha Menon"
        assert body["gaps"] == []
        assert body["raw_text"]

    def test_a_guest_gets_a_result_but_nothing_is_stored(
        self, client, mock_model, pdf_bytes, sample_profile
    ):
        mock_model(extract={"profile": sample_profile, "gaps": []})
        body = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
        ).json()
        # Registration is what makes results persist, not what makes them possible.
        assert body["profile"]["name"] == "Asha Menon"
        assert body["profile_id"] is None

    def test_a_non_pdf_is_rejected_by_content_not_by_filename(self, client, mock_model):
        mock_model()
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", b"just some text", "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "not_a_pdf"

    def test_an_oversized_upload_is_rejected(self, client, mock_model, monkeypatch):
        mock_model()
        monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
        monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)

        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", b"%PDF-" + b"0" * 4096, "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "file_too_large"

    def test_an_empty_upload_is_rejected(self, client, mock_model):
        mock_model()
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "empty_file"

    def test_a_pdf_with_no_extractable_text_is_rejected(self, client, mock_model, pdf_bytes):
        mock_model()
        response = client.post(
            "/api/parse-resume",
            files={"file": ("scan.pdf", pdf_bytes(" "), "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "no_text_in_pdf"

    def test_a_corrupt_pdf_is_reported_readably(self, client, mock_model):
        mock_model()
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 truncated garbage", "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] in {"unreadable_pdf", "no_text_in_pdf"}

    @pytest.mark.parametrize(
        "error,status",
        [
            (llm.LLMTimeoutError("slow"), 504),
            (llm.LLMUnavailableError("down"), 503),
            (llm.LLMInvalidJSONError("junk"), 502),
        ],
    )
    def test_model_failures_become_typed_http_errors(
        self, client, mock_model, pdf_bytes, error, status
    ):
        mock_model(raises=error)
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == status
        detail = response.json()["detail"]
        assert detail["code"] == error.code
        assert detail["retryable"] is True
        assert detail["stage"] == "extraction"


class TestInferTitles:
    def test_titles_come_back_in_client_shape(self, client, mock_model, sample_profile):
        mock_model(titles=[{"title": "Backend Engineer", "confidence": 90, "reason": "Python"}])
        response = client.post("/api/infer-titles", json={"profile": sample_profile})
        assert response.status_code == 200
        assert response.json()["titles"] == [
            {
                "id": "title-0",
                "title": "Backend Engineer",
                "matchPercentage": 90,
                "reason": "Python",
            }
        ]

    def test_an_empty_profile_is_rejected(self, client, mock_model):
        mock_model()
        response = client.post("/api/infer-titles", json={})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_profile"

    def test_model_failure_surfaces_with_its_stage(self, client, mock_model, sample_profile):
        mock_model(raises=llm.LLMUnavailableError("down"))
        response = client.post("/api/infer-titles", json={"profile": sample_profile})
        assert response.status_code == 503
        assert response.json()["detail"]["stage"] == "inference"


class TestSearchJobs:
    def test_mock_mode_returns_annotated_postings(self, client, monkeypatch, sample_profile):
        monkeypatch.setattr(config, "USE_MOCK_JOBS", True)
        response = client.post(
            "/api/jobs",
            json={
                "job_titles": [{"title": "Backend Engineer", "matchPercentage": 90}],
                "resume_profile": sample_profile,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["used_mock"] is True
        assert body["jobs"]
        # Every posting carries the free per-posting keyword signal...
        assert all("keyword_matches" in job for job in body["jobs"])
        # ...and none carries a fabricated per-job percentage.
        assert all("match" not in job for job in body["jobs"])

    def test_postings_are_sorted_by_keyword_overlap(self, client, monkeypatch, sample_profile):
        monkeypatch.setattr(config, "USE_MOCK_JOBS", True)
        body = client.post(
            "/api/jobs",
            json={"job_titles": [{"title": "X"}], "resume_profile": sample_profile},
        ).json()
        counts = [job["keyword_matches"] for job in body["jobs"]]
        assert counts == sorted(counts, reverse=True)

    def test_the_profile_is_optional(self, client, monkeypatch):
        monkeypatch.setattr(config, "USE_MOCK_JOBS", True)
        response = client.post("/api/jobs", json={"job_titles": [{"title": "X"}]})
        assert response.status_code == 200

    def test_no_titles_is_rejected(self, client):
        response = client.post("/api/jobs", json={"job_titles": []})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "no_titles"


class TestAnalyzeAts:
    def _analysis(self):
        return {
            "match_score": 72,
            "matched_skills": ["Python"],
            "missing_skills": ["Docker"],
            "recommendations": ["Add container experience"],
            "evidence": {"Python": "Python and SQL required."},
            "label": "Good Match",
            "summary": "Your resume is a good fit.",
            "corrected_skills": [],
        }

    def test_a_successful_analysis_returns_the_full_shape(
        self, client, mock_model, sample_profile, sample_job_description
    ):
        mock_model(analysis=self._analysis())
        response = client.post(
            "/api/analyze-ats",
            json={
                "resume_profile": sample_profile,
                "job_description": sample_job_description,
            },
        )
        assert response.status_code == 200
        analysis = response.json()["analysis"]
        assert analysis["match_score"] == 72
        assert analysis["label"] == "Good Match"
        assert analysis["evidence"]

    @pytest.mark.parametrize(
        "error,status",
        [
            (llm.LLMTimeoutError("slow"), 504),
            (llm.LLMUnavailableError("down"), 503),
            (llm.LLMInvalidJSONError("junk"), 502),
        ],
    )
    def test_a_failure_is_an_http_error_never_a_zero_score(
        self, client, mock_model, sample_profile, sample_job_description, error, status
    ):
        mock_model(raises=error)
        response = client.post(
            "/api/analyze-ats",
            json={
                "resume_profile": sample_profile,
                "job_description": sample_job_description,
            },
        )
        assert response.status_code == status
        body = response.json()
        assert "analysis" not in body
        assert body["detail"]["code"] == error.code
        assert body["detail"]["retryable"] is True

    def test_a_posting_with_no_description_is_rejected_up_front(
        self, client, mock_model, sample_profile
    ):
        mock_model()
        response = client.post(
            "/api/analyze-ats",
            json={"resume_profile": sample_profile, "job_description": "   "},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_job_description"

    def test_a_missing_profile_is_rejected(self, client, mock_model, sample_job_description):
        mock_model()
        response = client.post(
            "/api/analyze-ats",
            json={"resume_profile": {}, "job_description": sample_job_description},
        )
        assert response.status_code == 400


class TestCors:
    def test_wildcard_origin_is_not_configured(self):
        # "*" alongside credentials is rejected by browsers and unsafe once
        # authentication exists.
        assert "*" not in config.CORS_ORIGINS

    def test_a_configured_origin_is_allowed_with_credentials(self, client):
        response = client.get("/", headers={"Origin": config.CORS_ORIGINS[0]})
        assert response.headers["access-control-allow-origin"] == config.CORS_ORIGINS[0]
        # The session cookie cannot survive the cross-origin hop without this.
        assert response.headers.get("access-control-allow-credentials") == "true"
