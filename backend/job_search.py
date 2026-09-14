"""
Job discovery.

Searches every selected title concurrently against the JSearch aggregator,
normalises the results into one shape, and deduplicates across titles.

Two things are deliberate here:

**Quota is finite.** Each selected title costs one API call, so the mock path is
a first-class mode rather than a debugging afterthought - it turns on via
config, and turns on automatically when no key is present, so the pipeline still
works end to end for anyone without credentials.

**Partial results beat no results.** One title failing must not fail the search.
Failures are collected and reported alongside whatever did come back, so the UI
can say what was missed instead of silently showing a short list.
"""

import asyncio
import traceback
from typing import Any

import httpx

import config
from mock_jobs import MOCK_JOBS

_SEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"


def _format_location(job: dict[str, Any]) -> str:
    """Build a display location, falling back through the fields JSearch supplies."""
    parts = [job.get("job_city"), job.get("job_state"), job.get("job_country")]
    joined = ", ".join(part for part in parts if part)
    if joined:
        return joined
    return job.get("job_location") or "Location not specified"


def _normalise(job: dict[str, Any]) -> dict[str, Any]:
    """Map one raw JSearch posting onto the shape the rest of the app consumes."""
    return {
        "id": job.get("job_id"),
        "title": job.get("job_title") or "Untitled role",
        "company": job.get("employer_name") or "Unknown company",
        "location": _format_location(job),
        "type": job.get("job_employment_type"),
        "description": job.get("job_description") or "",
        "apply_link": job.get("job_apply_link") or job.get("job_google_link"),
        "is_remote": bool(job.get("job_is_remote", False)),
        "posted_at": job.get("job_posted_at_datetime_utc"),
        # Always an object, never a bare number - the two shapes diverging is
        # what made the mock path and the live path mutually incompatible.
        "salary": {
            "min": job.get("job_min_salary"),
            "max": job.get("job_max_salary"),
        },
    }


class TitleSearchFailed(Exception):
    """Raised internally so a per-title failure can be reported, not swallowed."""

    def __init__(self, title: str, reason: str, quota_exhausted: bool = False):
        self.title = title
        self.reason = reason
        self.quota_exhausted = quota_exhausted
        super().__init__(f"{title}: {reason}")


async def fetch_jobs_for_title(
    client: httpx.AsyncClient, title: str, country: str
) -> list[dict[str, Any]]:
    """Fetch one page of postings for a single title."""
    params = {
        "query": title,
        "country": country,
        "num_pages": 1,
        "date_posted": "month",
    }
    headers = {
        "X-RapidAPI-Key": config.RAPIDAPI_KEY or "",
        "X-RapidAPI-Host": config.RAPIDAPI_HOST,
    }

    try:
        response = await client.get(
            _SEARCH_URL,
            headers=headers,
            params=params,
            timeout=config.JOB_SEARCH_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 429:
            raise TitleSearchFailed(
                title,
                "The job search quota has been used up for now.",
                quota_exhausted=True,
            ) from exc
        if status in (401, 403):
            raise TitleSearchFailed(
                title, "The job search API rejected the configured key."
            ) from exc
        raise TitleSearchFailed(title, f"Job search returned HTTP {status}.") from exc
    except httpx.TimeoutException as exc:
        raise TitleSearchFailed(title, "Job search timed out.") from exc
    except httpx.HTTPError as exc:
        raise TitleSearchFailed(title, f"Job search failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise TitleSearchFailed(title, "Job search returned an unreadable response.") from exc

    raw_jobs = (data.get("data") or {}).get("jobs") or []
    return [_normalise(job) for job in raw_jobs if job.get("job_id")]


def _mock_results() -> list[dict[str, Any]]:
    """Return a copy of the sample postings, so callers can annotate them freely."""
    return [dict(job) for job in MOCK_JOBS]


async def search_all_jobs(
    job_titles: list[dict[str, Any]],
    country: str | None = None,
) -> dict[str, Any]:
    """
    Search every supplied title concurrently and merge the results.

    Returns:
        {
          "jobs": [...],        # deduplicated across titles
          "warnings": [...],    # human-readable notes about what did not work
          "used_mock": bool,    # whether sample data was served
          "quota_exhausted": bool,
        }
    """
    country = country or config.DEFAULT_COUNTRY
    titles = [
        str(entry.get("title")).strip()
        for entry in job_titles
        if isinstance(entry, dict) and str(entry.get("title") or "").strip()
    ]

    if not titles:
        return {"jobs": [], "warnings": ["No job titles were selected."],
                "used_mock": False, "quota_exhausted": False}

    if config.USE_MOCK_JOBS:
        reason = (
            "Showing sample postings because no job search API key is configured."
            if config.RAPIDAPI_KEY is None
            else "Showing sample postings (mock mode is on, no API quota used)."
        )
        print(f"[jobs] {reason}")
        return {
            "jobs": _mock_results(),
            "warnings": [reason],
            "used_mock": True,
            "quota_exhausted": False,
        }

    print(f"[jobs] searching {len(titles)} title(s) in '{country}'")

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(fetch_jobs_for_title(client, title, country) for title in titles),
            return_exceptions=True,
        )

    jobs: list[dict[str, Any]] = []
    warnings: list[str] = []
    quota_exhausted = False

    for title, result in zip(titles, results):
        if isinstance(result, TitleSearchFailed):
            warnings.append(f"'{result.title}' could not be searched. {result.reason}")
            quota_exhausted = quota_exhausted or result.quota_exhausted
            continue
        if isinstance(result, BaseException):
            print(f"[jobs] unexpected failure for '{title}':")
            traceback.print_exception(type(result), result, result.__traceback__)
            warnings.append(f"'{title}' could not be searched.")
            continue
        jobs.extend(result)

    # Deduplicate across titles, keeping first occurrence.
    unique: dict[str, dict[str, Any]] = {}
    for job in jobs:
        job_id = job.get("id")
        if job_id and job_id not in unique:
            unique[job_id] = job

    print(f"[jobs] {len(unique)} unique posting(s), {len(warnings)} warning(s)")

    return {
        "jobs": list(unique.values()),
        "warnings": warnings,
        "used_mock": False,
        "quota_exhausted": quota_exhausted,
    }
