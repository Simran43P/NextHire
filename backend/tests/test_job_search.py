"""
Stage 3 contract: titles -> normalised, deduplicated postings.

No test here makes a network call. Live searching is exercised by substituting
a fake fetcher, so the suite never spends job-search API quota.
"""

import httpx
import pytest

import config
import job_search
from job_search import TitleSearchFailed, _normalise, search_all_jobs


def raw_posting(**overrides):
    posting = {
        "job_id": "abc123",
        "job_title": "Backend Engineer",
        "employer_name": "Acme",
        "job_city": "Kochi",
        "job_state": "Kerala",
        "job_country": "IN",
        "job_employment_type": "FULLTIME",
        "job_description": "Python and SQL",
        "job_apply_link": "https://example.com/apply",
        "job_is_remote": True,
        "job_posted_at_datetime_utc": "2026-09-01T00:00:00Z",
        "job_min_salary": 600000,
        "job_max_salary": 900000,
    }
    posting.update(overrides)
    return posting


class TestNormalise:
    def test_maps_every_field_to_the_client_shape(self):
        job = _normalise(raw_posting())
        assert job["id"] == "abc123"
        assert job["company"] == "Acme"
        assert job["location"] == "Kochi, Kerala, IN"
        assert job["salary"] == {"min": 600000, "max": 900000}

    def test_salary_is_always_an_object_even_when_unknown(self):
        # The mock path used a bare number while the live path used an object.
        # Any UI rendering salary broke the moment mocks were switched off.
        job = _normalise(raw_posting(job_min_salary=None, job_max_salary=None))
        assert job["salary"] == {"min": None, "max": None}

    def test_location_falls_back_when_city_and_state_are_absent(self):
        job = _normalise(
            raw_posting(job_city=None, job_state=None, job_country=None,
                        job_location="Remote, India")
        )
        assert job["location"] == "Remote, India"

    def test_location_of_last_resort(self):
        job = _normalise(
            raw_posting(job_city=None, job_state=None, job_country=None, job_location=None)
        )
        assert job["location"] == "Location not specified"

    def test_missing_company_and_title_get_readable_placeholders(self):
        job = _normalise(raw_posting(employer_name=None, job_title=None))
        assert job["company"] == "Unknown company"
        assert job["title"] == "Untitled role"

    def test_apply_link_falls_back_to_the_google_link(self):
        job = _normalise(raw_posting(job_apply_link=None, job_google_link="https://g/x"))
        assert job["apply_link"] == "https://g/x"

    def test_mock_postings_share_the_live_shape(self):
        from mock_jobs import MOCK_JOBS

        live_keys = set(_normalise(raw_posting()))
        for posting in MOCK_JOBS:
            assert live_keys == set(posting), f"{posting['id']} diverges from live shape"
            assert isinstance(posting["salary"], dict)


class TestMockMode:
    async def test_mock_mode_returns_samples_and_spends_no_quota(self, monkeypatch):
        monkeypatch.setattr(config, "USE_MOCK_JOBS", True)

        async def _explode(*args, **kwargs):
            raise AssertionError("mock mode must not contact the API")

        monkeypatch.setattr(job_search, "fetch_jobs_for_title", _explode)

        result = await search_all_jobs([{"title": "Backend Engineer"}])
        assert result["used_mock"] is True
        assert len(result["jobs"]) > 0
        assert result["warnings"]

    async def test_missing_key_forces_mock_mode_at_import_time(self):
        # config.USE_MOCK_JOBS is True whenever no key is configured, which is
        # what lets the app work end to end with no credentials.
        assert config.RAPIDAPI_KEY is not None or config.USE_MOCK_JOBS is True


class TestSearchAllJobs:
    @pytest.fixture(autouse=True)
    def _live_mode(self, monkeypatch):
        monkeypatch.setattr(config, "USE_MOCK_JOBS", False)
        monkeypatch.setattr(config, "RAPIDAPI_KEY", "test-key")

    def _fake_fetcher(self, monkeypatch, behaviour):
        async def _fetch(client, title, country):
            return behaviour(title)

        monkeypatch.setattr(job_search, "fetch_jobs_for_title", _fetch)

    async def test_results_are_merged_and_deduplicated_across_titles(self, monkeypatch):
        def behaviour(title):
            shared = _normalise(raw_posting(job_id="shared"))
            unique = _normalise(raw_posting(job_id=f"{title}-only"))
            return [shared, unique]

        self._fake_fetcher(monkeypatch, behaviour)
        result = await search_all_jobs([{"title": "A"}, {"title": "B"}])

        ids = sorted(job["id"] for job in result["jobs"])
        assert ids == ["A-only", "B-only", "shared"]

    async def test_one_title_failing_does_not_fail_the_search(self, monkeypatch):
        def behaviour(title):
            if title == "Broken":
                raise TitleSearchFailed("Broken", "Job search timed out.")
            return [_normalise(raw_posting(job_id=title))]

        self._fake_fetcher(monkeypatch, behaviour)
        result = await search_all_jobs([{"title": "Good"}, {"title": "Broken"}])

        assert [job["id"] for job in result["jobs"]] == ["Good"]
        assert any("Broken" in warning for warning in result["warnings"])

    async def test_quota_exhaustion_is_reported_distinctly(self, monkeypatch):
        def behaviour(title):
            raise TitleSearchFailed(title, "quota used up", quota_exhausted=True)

        self._fake_fetcher(monkeypatch, behaviour)
        result = await search_all_jobs([{"title": "A"}])
        assert result["quota_exhausted"] is True
        assert result["jobs"] == []

    async def test_an_unexpected_exception_is_contained(self, monkeypatch):
        def behaviour(title):
            raise RuntimeError("something odd")

        self._fake_fetcher(monkeypatch, behaviour)
        result = await search_all_jobs([{"title": "A"}])
        assert result["jobs"] == []
        assert result["warnings"]

    async def test_blank_and_malformed_titles_are_skipped(self, monkeypatch):
        seen = []

        async def _fetch(client, title, country):
            seen.append(title)
            return []

        monkeypatch.setattr(job_search, "fetch_jobs_for_title", _fetch)
        await search_all_jobs([{"title": "  "}, {"title": "Real"}, "junk", {}])
        assert seen == ["Real"]

    async def test_no_usable_titles_returns_a_warning_not_an_error(self):
        result = await search_all_jobs([{"title": "   "}])
        assert result["jobs"] == []
        assert result["warnings"]


class TestFetchErrorMapping:
    async def _fetch_with_status(self, monkeypatch, status):
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(status, request=request)

        class _Client:
            async def get(self, *args, **kwargs):
                raise httpx.HTTPStatusError("boom", request=request, response=response)

        return await job_search.fetch_jobs_for_title(_Client(), "Backend Engineer", "in")

    async def test_429_is_flagged_as_quota_exhaustion(self, monkeypatch):
        with pytest.raises(TitleSearchFailed) as exc:
            await self._fetch_with_status(monkeypatch, 429)
        assert exc.value.quota_exhausted is True

    async def test_auth_failure_is_explained(self, monkeypatch):
        with pytest.raises(TitleSearchFailed) as exc:
            await self._fetch_with_status(monkeypatch, 401)
        assert "key" in exc.value.reason.lower()

    async def test_timeout_is_reported_as_a_timeout(self):
        class _Client:
            async def get(self, *args, **kwargs):
                raise httpx.ReadTimeout("slow")

        with pytest.raises(TitleSearchFailed) as exc:
            await job_search.fetch_jobs_for_title(_Client(), "A", "in")
        assert "timed out" in exc.value.reason.lower()
