"""
Saving pipeline output, and reading it back with ownership enforced.

Every read here takes a `user_id` and filters on it in the query itself, rather
than fetching a row and checking afterwards. That ordering matters: a check that
happens after the fetch is a check somebody eventually forgets, and the result
is one candidate reading another's resume.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    AtsAnalysis,
    InferredTitle,
    Job,
    JobSearch,
    Profile,
    Resume,
    utcnow,
)


# ---------------------------------------------------------------------------
# Resumes and profiles
# ---------------------------------------------------------------------------


async def save_resume_and_profile(
    db: AsyncSession,
    *,
    user_id: int,
    filename: str,
    storage_key: str,
    raw_text: str,
    profile_data: dict[str, Any],
    gaps: list[str],
    model: str,
) -> Profile:
    resume = Resume(
        user_id=user_id,
        original_filename=filename or "",
        storage_key=storage_key,
        raw_text=raw_text,
    )
    db.add(resume)
    await db.flush()

    profile = Profile(
        resume_id=resume.id,
        user_id=user_id,
        data=profile_data,
        gaps=gaps,
        extraction_model=model,
        version=1,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_profile(db: AsyncSession, profile_id: int, user_id: int) -> Profile | None:
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_profiles(db: AsyncSession, user_id: int) -> list[Profile]:
    result = await db.execute(
        select(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Profile.created_at.desc())
    )
    return list(result.scalars())


async def update_profile(
    db: AsyncSession, profile: Profile, data: dict[str, Any]
) -> Profile:
    """
    Persist a corrected profile and bump its version.

    The version bump is what invalidates cached analyses: they key on
    (profile_id, job_id, profile_version), so a correction silently keeping old
    scores is structurally impossible rather than merely unlikely.
    """
    profile.data = data
    profile.version += 1
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_resume_for_profile(
    db: AsyncSession, profile_id: int, user_id: int
) -> Resume | None:
    result = await db.execute(
        select(Resume)
        .join(Profile, Profile.resume_id == Resume.id)
        .where(Profile.id == profile_id, Resume.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------


async def save_inferred_titles(
    db: AsyncSession, profile_id: int, titles: list[dict[str, Any]]
) -> None:
    await db.execute(
        delete(InferredTitle).where(InferredTitle.profile_id == profile_id)
    )
    for entry in titles:
        db.add(
            InferredTitle(
                profile_id=profile_id,
                title=entry.get("title", ""),
                confidence=int(entry.get("matchPercentage", entry.get("confidence", 0))),
                reason=entry.get("reason", "") or "",
            )
        )
    await db.commit()


async def mark_titles_selected(
    db: AsyncSession, profile_id: int, selected: list[str]
) -> None:
    wanted = {title.strip().lower() for title in selected}
    result = await db.execute(
        select(InferredTitle).where(InferredTitle.profile_id == profile_id)
    )
    for row in result.scalars():
        row.is_selected = row.title.strip().lower() in wanted
    await db.commit()


# ---------------------------------------------------------------------------
# Searches and postings
# ---------------------------------------------------------------------------


async def save_search(
    db: AsyncSession,
    *,
    profile_id: int,
    titles: list[dict[str, Any]],
    country: str,
    jobs: list[dict[str, Any]],
    warnings: list[str],
    used_mock: bool,
) -> tuple[JobSearch, list[Job]]:
    search = JobSearch(
        profile_id=profile_id,
        titles_searched=[entry.get("title", "") for entry in titles],
        country=country,
        result_count=len(jobs),
        used_mock=used_mock,
        warnings=warnings,
    )
    db.add(search)
    await db.flush()

    rows: list[Job] = []
    seen: set[str] = set()
    for job in jobs:
        external_id = str(job.get("id") or "")
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        salary = job.get("salary") or {}
        row = Job(
            search_id=search.id,
            external_id=external_id,
            title=job.get("title") or "",
            company=job.get("company") or "",
            location=job.get("location") or "",
            employment_type=job.get("type"),
            description=job.get("description") or "",
            apply_link=job.get("apply_link"),
            is_remote=bool(job.get("is_remote")),
            posted_at=job.get("posted_at"),
            salary_min=salary.get("min") if isinstance(salary, dict) else None,
            salary_max=salary.get("max") if isinstance(salary, dict) else None,
            keyword_matches=int(job.get("keyword_matches") or 0),
            matched_keywords=job.get("matched_keywords") or [],
        )
        db.add(row)
        rows.append(row)

    await db.commit()
    for row in rows:
        await db.refresh(row)
    return search, rows


def job_to_api(row: Job) -> dict[str, Any]:
    """Render a stored posting in the shape the client already consumes."""
    return {
        "id": row.external_id,
        "job_id": row.id,
        "title": row.title,
        "company": row.company,
        "location": row.location,
        "type": row.employment_type,
        "description": row.description,
        "apply_link": row.apply_link,
        "is_remote": row.is_remote,
        "posted_at": row.posted_at,
        "salary": {"min": row.salary_min, "max": row.salary_max},
        "keyword_matches": row.keyword_matches,
        "matched_keywords": row.matched_keywords,
    }


async def get_job(db: AsyncSession, job_id: int, user_id: int) -> Job | None:
    """Fetch a posting, but only through a search belonging to this user."""
    result = await db.execute(
        select(Job)
        .join(JobSearch, JobSearch.id == Job.search_id)
        .join(Profile, Profile.id == JobSearch.profile_id)
        .where(Job.id == job_id, Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


async def find_cached_analysis(
    db: AsyncSession, *, profile_id: int, job_id: int, profile_version: int
) -> AtsAnalysis | None:
    result = await db.execute(
        select(AtsAnalysis).where(
            AtsAnalysis.profile_id == profile_id,
            AtsAnalysis.job_id == job_id,
            AtsAnalysis.profile_version == profile_version,
        )
    )
    return result.scalar_one_or_none()


async def save_analysis(
    db: AsyncSession,
    *,
    profile_id: int,
    job_id: int,
    profile_version: int,
    analysis: dict[str, Any],
    model: str,
) -> AtsAnalysis:
    existing = await find_cached_analysis(
        db, profile_id=profile_id, job_id=job_id, profile_version=profile_version
    )
    row = existing or AtsAnalysis(
        profile_id=profile_id, job_id=job_id, profile_version=profile_version
    )

    row.match_score = analysis["match_score"]
    row.label = analysis["label"]
    row.summary = analysis["summary"]
    row.matched_skills = analysis["matched_skills"]
    row.missing_skills = analysis["missing_skills"]
    row.recommendations = analysis["recommendations"]
    row.evidence = analysis["evidence"]
    row.corrected_skills = analysis["corrected_skills"]
    row.model = model

    if existing is None:
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def analysis_to_api(row: AtsAnalysis) -> dict[str, Any]:
    return {
        "match_score": row.match_score,
        "matched_skills": row.matched_skills,
        "missing_skills": row.missing_skills,
        "recommendations": row.recommendations,
        "evidence": row.evidence,
        "label": row.label,
        "summary": row.summary,
        "corrected_skills": row.corrected_skills,
        "cached": True,
        "analysed_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------------------------------------------------------------------------
# Account-wide
# ---------------------------------------------------------------------------


async def count_profiles(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Profile).where(Profile.user_id == user_id)
    )
    return int(result.scalar() or 0)


async def export_everything(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """Everything the system holds about one user, as plain JSON."""
    profiles = await list_profiles(db, user_id)
    profile_ids = [profile.id for profile in profiles]

    resumes_result = await db.execute(select(Resume).where(Resume.user_id == user_id))
    resumes = list(resumes_result.scalars())

    titles: list[InferredTitle] = []
    searches: list[JobSearch] = []
    jobs: list[Job] = []
    analyses: list[AtsAnalysis] = []

    if profile_ids:
        titles = list(
            (
                await db.execute(
                    select(InferredTitle).where(
                        InferredTitle.profile_id.in_(profile_ids)
                    )
                )
            ).scalars()
        )
        searches = list(
            (
                await db.execute(
                    select(JobSearch).where(JobSearch.profile_id.in_(profile_ids))
                )
            ).scalars()
        )
        search_ids = [search.id for search in searches]
        if search_ids:
            jobs = list(
                (
                    await db.execute(select(Job).where(Job.search_id.in_(search_ids)))
                ).scalars()
            )
        analyses = list(
            (
                await db.execute(
                    select(AtsAnalysis).where(AtsAnalysis.profile_id.in_(profile_ids))
                )
            ).scalars()
        )

    return {
        "exported_at": utcnow().isoformat(),
        "resumes": [
            {
                "id": row.id,
                "original_filename": row.original_filename,
                "raw_text": row.raw_text,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in resumes
        ],
        "profiles": [
            {
                "id": row.id,
                "resume_id": row.resume_id,
                "version": row.version,
                "extraction_model": row.extraction_model,
                "gaps": row.gaps,
                "data": row.data,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in profiles
        ],
        "inferred_titles": [
            {
                "profile_id": row.profile_id,
                "title": row.title,
                "confidence": row.confidence,
                "reason": row.reason,
                "is_selected": row.is_selected,
            }
            for row in titles
        ],
        "job_searches": [
            {
                "id": row.id,
                "profile_id": row.profile_id,
                "titles_searched": row.titles_searched,
                "country": row.country,
                "result_count": row.result_count,
                "used_mock": row.used_mock,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in searches
        ],
        "jobs": [job_to_api(row) | {"search_id": row.search_id} for row in jobs],
        "ats_analyses": [
            analysis_to_api(row)
            | {"profile_id": row.profile_id, "job_id": row.job_id,
               "profile_version": row.profile_version, "model": row.model}
            for row in analyses
        ],
    }
