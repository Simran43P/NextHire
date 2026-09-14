"""
Everything that helps after the analysis: cover letters, interview questions,
and the skills gap across every posting analysed so far.

The gap endpoint is the odd one out and the cheapest thing here: it needs no
model call at all, only arithmetic over results already stored. One analysis
tells you what a posting wants; ten tell you what the market you are applying
into wants.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import config
import cover_letter as cover_letter_service
import errors
import gap as gap_service
import interview as interview_service
import llm
import persistence
import ratelimit
import resume_pdf
import tasks
from db import get_db, get_sessionmaker
from models import AtsAnalysis, CoverLetter, InterviewPrep, Job, Profile, User

router = APIRouter(prefix="/api", tags=["prep"])


class CoverLetterRequest(BaseModel):
    profile_id: int | None = None
    job_id: int | None = None
    profile: dict[str, Any] | None = None
    job: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    tone: str = cover_letter_service.DEFAULT_TONE


class SaveCoverLetterRequest(BaseModel):
    content: str


class RenderLetterRequest(BaseModel):
    content: str
    name: str = ""


class InterviewRequest(BaseModel):
    profile_id: int | None = None
    job_id: int | None = None
    profile: dict[str, Any] | None = None
    job: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Background handlers
# ---------------------------------------------------------------------------


@tasks.register("cover-letter")
async def _run_cover_letter(payload: dict[str, Any]) -> dict[str, Any]:
    result = await cover_letter_service.generate(
        payload["profile"], payload["job"], payload["analysis"], payload["tone"]
    )
    if payload.get("profile_id") and payload.get("job_id"):
        async with get_sessionmaker()() as db:
            result["cover_letter_id"] = await _store_letter(
                db,
                profile_id=payload["profile_id"],
                job_id=payload["job_id"],
                result=result,
            )
    return result


@tasks.register("interview")
async def _run_interview(payload: dict[str, Any]) -> dict[str, Any]:
    questions = await interview_service.generate(
        payload["profile"], payload["job"], payload["analysis"]
    )
    if payload.get("profile_id") and payload.get("job_id"):
        async with get_sessionmaker()() as db:
            await _store_prep(
                db,
                profile_id=payload["profile_id"],
                job_id=payload["job_id"],
                profile_version=payload["profile_version"],
                questions=questions,
            )
    return {"questions": questions}


async def _store_letter(
    db: AsyncSession, *, profile_id: int, job_id: int, result: dict[str, Any]
) -> int:
    row = CoverLetter(
        profile_id=profile_id,
        job_id=job_id,
        tone=result["tone"],
        content=result["letter"],
        unsupported_claims=result["unsupported"],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row.id


async def _store_prep(
    db: AsyncSession,
    *,
    profile_id: int,
    job_id: int,
    profile_version: int,
    questions: dict[str, Any],
) -> InterviewPrep:
    existing = (
        await db.execute(
            select(InterviewPrep).where(
                InterviewPrep.profile_id == profile_id,
                InterviewPrep.job_id == job_id,
                InterviewPrep.profile_version == profile_version,
            )
        )
    ).scalar_one_or_none()

    row = existing or InterviewPrep(
        profile_id=profile_id, job_id=job_id, profile_version=profile_version
    )
    row.questions = questions
    row.model = config.OLLAMA_MODEL
    if existing is None:
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Shared resolution
# ---------------------------------------------------------------------------


async def _resolve(
    db: AsyncSession,
    user: User | None,
    *,
    profile_id: int | None,
    job_id: int | None,
    inline_profile: dict[str, Any] | None,
    inline_job: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], int | None, int | None]:
    """Return (profile, job, profile_id, profile_version)."""
    if profile_id is not None:
        if user is None:
            raise auth.forbidden()
        stored = await persistence.get_profile(db, profile_id, user.id)
        if stored is None:
            raise auth.forbidden()
        profile, resolved_id, version = stored.data, stored.id, stored.version
    else:
        if not inline_profile:
            raise errors.bad_request("missing_profile", "A resume profile is required.")
        profile, resolved_id, version = inline_profile, None, None

    if job_id is not None:
        if user is None:
            raise auth.forbidden()
        stored_job = await persistence.get_job(db, job_id, user.id)
        if stored_job is None:
            raise auth.forbidden()
        job = {
            "title": stored_job.title,
            "company": stored_job.company,
            "description": stored_job.description,
        }
    else:
        job = inline_job or {}

    if not str(job.get("description") or "").strip():
        raise errors.bad_request(
            "missing_job_description",
            "This posting has no description, so there is nothing to work from.",
        )

    return profile, job, resolved_id, version


async def _analysis_for(
    db: AsyncSession,
    supplied: dict[str, Any] | None,
    profile_id: int | None,
    job_id: int | None,
    version: int | None,
) -> dict[str, Any]:
    if supplied is not None:
        return supplied
    if profile_id is not None and job_id is not None:
        cached = await persistence.find_cached_analysis(
            db, profile_id=profile_id, job_id=job_id, profile_version=version
        )
        if cached is not None:
            return persistence.analysis_to_api(cached)
    return {"matched_skills": [], "missing_skills": []}


# ---------------------------------------------------------------------------
# Cover letters
# ---------------------------------------------------------------------------


@router.post("/cover-letter")
async def make_cover_letter(
    request: Request,
    payload: CoverLetterRequest,
    background: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Write a cover letter for one posting.

    Unsupported claims are located rather than removed. A letter is one piece of
    prose - discarding it over a single overreaching sentence would leave the
    candidate with nothing - so the sentences that need checking come back
    alongside it, and the letter is editable.
    """
    ratelimit.check(
        request,
        "inference",
        config.RATE_LIMIT_INFERENCE_PER_HOUR,
        user_id=user.id if user else None,
    )

    profile, job, profile_id, version = await _resolve(
        db,
        user,
        profile_id=payload.profile_id,
        job_id=payload.job_id,
        inline_profile=payload.profile,
        inline_job=payload.job,
    )
    analysis = await _analysis_for(db, payload.analysis, profile_id, payload.job_id, version)

    if user is not None and background:
        task = await tasks.enqueue(
            user.id,
            "cover-letter",
            {
                "profile": profile,
                "job": job,
                "analysis": analysis,
                "tone": payload.tone,
                "profile_id": profile_id,
                "job_id": payload.job_id,
            },
        )
        return {"status": "queued", "task_id": task.id}

    try:
        result = await cover_letter_service.generate(profile, job, analysis, payload.tone)
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "cover-letter")
    except Exception as exc:
        raise errors.unexpected(exc, "cover-letter")

    letter_id = None
    if profile_id is not None and payload.job_id is not None:
        letter_id = await _store_letter(
            db, profile_id=profile_id, job_id=payload.job_id, result=result
        )

    return {"status": "success", **result, "cover_letter_id": letter_id}


@router.patch("/cover-letters/{letter_id}")
async def save_cover_letter(
    letter_id: int,
    payload: SaveCoverLetterRequest,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save an edited letter, re-checking it.

    The check runs again on save rather than only on generation, because the
    candidate can type a claim in themselves - and a warning that only ever
    applied to the model's draft would be worth very little.
    """
    result = await db.execute(
        select(CoverLetter, Profile, Job)
        .join(Profile, Profile.id == CoverLetter.profile_id)
        .join(Job, Job.id == CoverLetter.job_id)
        .where(CoverLetter.id == letter_id, Profile.user_id == user.id)
    )
    row = result.first()
    if row is None:
        raise auth.forbidden()

    letter, profile, job = row
    letter.content = payload.content.strip()
    letter.unsupported_claims = cover_letter_service.locate_unsupported(
        letter.content,
        profile.data,
        {"company": job.company, "title": job.title},
    )
    await db.commit()

    return {
        "status": "success",
        "letter": letter.content,
        "unsupported": letter.unsupported_claims,
    }


@router.get("/cover-letters")
async def list_cover_letters(
    job_id: int | None = Query(default=None),
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(CoverLetter)
        .join(Profile, Profile.id == CoverLetter.profile_id)
        .where(Profile.user_id == user.id)
        .order_by(CoverLetter.created_at.desc())
    )
    if job_id is not None:
        query = query.where(CoverLetter.job_id == job_id)

    rows = list((await db.execute(query)).scalars())
    return {
        "status": "success",
        "cover_letters": [
            {
                "id": row.id,
                "job_id": row.job_id,
                "tone": row.tone,
                "content": row.content,
                "unsupported": row.unsupported_claims,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.post("/cover-letter/pdf")
async def render_cover_letter(payload: RenderLetterRequest):
    """Render a letter as a plain, parseable PDF."""
    if not payload.content.strip():
        raise errors.bad_request("empty_letter", "There is nothing to export yet.")
    content = resume_pdf.render_letter(payload.content, name=payload.name)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="cover-letter.pdf"'},
    )


# ---------------------------------------------------------------------------
# Interview preparation
# ---------------------------------------------------------------------------


@router.post("/interview-prep")
async def make_interview_prep(
    request: Request,
    payload: InterviewRequest,
    background: bool = Query(default=False),
    refresh: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Likely interview questions, split technical / behavioural / gap-probing."""
    ratelimit.check(
        request,
        "inference",
        config.RATE_LIMIT_INFERENCE_PER_HOUR,
        user_id=user.id if user else None,
    )

    profile, job, profile_id, version = await _resolve(
        db,
        user,
        profile_id=payload.profile_id,
        job_id=payload.job_id,
        inline_profile=payload.profile,
        inline_job=payload.job,
    )

    cacheable = profile_id is not None and payload.job_id is not None
    if cacheable and not refresh:
        cached = (
            await db.execute(
                select(InterviewPrep).where(
                    InterviewPrep.profile_id == profile_id,
                    InterviewPrep.job_id == payload.job_id,
                    InterviewPrep.profile_version == version,
                )
            )
        ).scalar_one_or_none()
        if cached is not None:
            return {"status": "success", "questions": cached.questions, "cached": True}

    analysis = await _analysis_for(db, payload.analysis, profile_id, payload.job_id, version)

    if user is not None and background:
        task = await tasks.enqueue(
            user.id,
            "interview",
            {
                "profile": profile,
                "job": job,
                "analysis": analysis,
                "profile_id": profile_id,
                "job_id": payload.job_id,
                "profile_version": version or 1,
            },
        )
        return {"status": "queued", "task_id": task.id}

    try:
        questions = await interview_service.generate(profile, job, analysis)
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "interview")
    except Exception as exc:
        raise errors.unexpected(exc, "interview")

    if cacheable:
        await _store_prep(
            db,
            profile_id=profile_id,
            job_id=payload.job_id,
            profile_version=version or 1,
            questions=questions,
        )

    return {"status": "success", "questions": questions, "cached": False}


# ---------------------------------------------------------------------------
# Skills gap
# ---------------------------------------------------------------------------


@router.get("/skills-gap")
async def skills_gap(
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    What is costing this candidate across every posting they have analysed.

    No model call: the answer is already in the stored analyses, and the lift
    estimate re-runs the real scoring rule with one more skill supported rather
    than inventing a number.
    """
    rows = (
        await db.execute(
            select(AtsAnalysis, Job)
            .join(Profile, Profile.id == AtsAnalysis.profile_id)
            .join(Job, Job.id == AtsAnalysis.job_id)
            .where(Profile.user_id == user.id)
        )
    ).all()

    analyses = [
        {
            "job_id": analysis.job_id,
            "title": job.title,
            "company": job.company,
            "match_score": analysis.match_score,
            "missing_skills": analysis.missing_skills,
            "evidence": analysis.evidence,
        }
        for analysis, job in rows
    ]

    return {"status": "success", **gap_service.analyse_gaps(analyses)}
