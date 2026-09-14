"""
Resume optimisation.

Three steps, deliberately separate:

    POST /api/optimize        propose edits, each one reviewable
    POST /api/optimize/apply  apply the accepted subset and re-score
    GET  .../pdf              render the result as an ATS-safe PDF

They are separate because the candidate has to be able to see every change
before it happens. A single "improve my resume" button that returns finished
text asks them to trust a 3B model with their employment history, which is not
a reasonable thing to ask.

The PDF is rendered on demand from the stored profile rather than saved as a
file. It is a pure function of that profile, so regenerating is both cheaper
than storing and incapable of going stale.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import config
import errors
import llm
import optimizer
import persistence
import ratelimit
import resume_pdf
import tasks
from ats_matcher import analyze_job_match
from db import get_db, get_sessionmaker
from models import TailoredResume, User

router = APIRouter(prefix="/api", tags=["optimize"])


class OptimizeRequest(BaseModel):
    profile_id: int | None = None
    job_id: int | None = None
    # Guest path: everything supplied inline, nothing stored.
    profile: dict[str, Any] | None = None
    job_description: str | None = None
    analysis: dict[str, Any] | None = None


class ApplyRequest(BaseModel):
    changes: list[dict[str, Any]] = Field(default_factory=list)
    accepted_ids: list[str] = Field(default_factory=list)
    rejected_changes: list[dict[str, Any]] = Field(default_factory=list)
    profile_id: int | None = None
    job_id: int | None = None
    profile: dict[str, Any] | None = None
    job_description: str | None = None
    before_score: int | None = None


class RenderRequest(BaseModel):
    profile: dict[str, Any]
    template: str | None = None


# ---------------------------------------------------------------------------
# Background handlers
# ---------------------------------------------------------------------------


@tasks.register("optimise")
async def _run_optimise(payload: dict[str, Any]) -> dict[str, Any]:
    return await optimizer.propose_optimisations(
        payload["profile"], payload["job_description"], payload["analysis"]
    )


@tasks.register("tailor")
async def _run_tailor(payload: dict[str, Any]) -> dict[str, Any]:
    tailored = optimizer.apply_changes(
        payload["profile"], payload["changes"], payload["accepted_ids"]
    )
    after = await analyze_job_match(
        resume_profile=tailored, job_description=payload["job_description"]
    )

    record_id = None
    if payload.get("profile_id") and payload.get("job_id"):
        async with get_sessionmaker()() as db:
            record_id = await _store(
                db,
                profile_id=payload["profile_id"],
                job_id=payload["job_id"],
                profile_version=payload["profile_version"],
                tailored=tailored,
                changes=payload["changes"],
                accepted_ids=payload["accepted_ids"],
                rejected=payload.get("rejected_changes") or [],
                before_score=payload.get("before_score"),
                after_score=after["match_score"],
            )

    return {
        "tailored_profile": tailored,
        "after_analysis": after,
        "before_score": payload.get("before_score"),
        "after_score": after["match_score"],
        "tailored_resume_id": record_id,
    }


async def _store(
    db: AsyncSession,
    *,
    profile_id: int,
    job_id: int,
    profile_version: int,
    tailored: dict[str, Any],
    changes: list[dict[str, Any]],
    accepted_ids: list[str],
    rejected: list[dict[str, Any]],
    before_score: int | None,
    after_score: int | None,
) -> int:
    record = TailoredResume(
        profile_id=profile_id,
        job_id=job_id,
        profile_version=profile_version,
        tailored_profile=tailored,
        changes=changes,
        accepted_ids=accepted_ids,
        rejected_changes=rejected,
        before_score=before_score,
        after_score=after_score,
        content=resume_pdf.extract_text(resume_pdf.render(tailored)),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record.id


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
    inline_description: str | None,
) -> tuple[dict[str, Any], str, int | None, int | None]:
    """Return (profile, job_description, profile_id, profile_version)."""
    profile, resolved_id, version = await _profile(db, user, profile_id, inline_profile)

    description = inline_description
    if job_id is not None:
        if user is None:
            raise auth.forbidden()
        job = await persistence.get_job(db, job_id, user.id)
        if job is None:
            raise auth.forbidden()
        description = job.description

    if not (description or "").strip():
        raise errors.bad_request(
            "missing_job_description",
            "This posting has no description, so it cannot be optimised against.",
        )

    return profile, description, resolved_id, version


async def _profile(
    db: AsyncSession,
    user: User | None,
    profile_id: int | None,
    inline: dict[str, Any] | None,
) -> tuple[dict[str, Any], int | None, int | None]:
    if profile_id is not None:
        if user is None:
            raise auth.forbidden()
        stored = await persistence.get_profile(db, profile_id, user.id)
        if stored is None:
            raise auth.forbidden()
        return stored.data, stored.id, stored.version

    if not inline:
        raise errors.bad_request("missing_profile", "A resume profile is required.")
    return inline, None, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/optimize")
async def propose(
    request: Request,
    payload: OptimizeRequest,
    background: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Propose tailored edits for one posting.

    Every proposal has already passed the fabrication guard. Anything that
    introduced a claim the profile does not support is returned separately
    under `rejected` rather than dropped quietly - a candidate is better served
    knowing four suggestions were thrown out on their behalf.
    """
    ratelimit.check(
        request,
        "inference",
        config.RATE_LIMIT_INFERENCE_PER_HOUR,
        user_id=user.id if user else None,
    )

    profile, description, profile_id, version = await _resolve(
        db,
        user,
        profile_id=payload.profile_id,
        job_id=payload.job_id,
        inline_profile=payload.profile,
        inline_description=payload.job_description,
    )

    analysis = payload.analysis
    if analysis is None and profile_id is not None and payload.job_id is not None:
        cached = await persistence.find_cached_analysis(
            db, profile_id=profile_id, job_id=payload.job_id, profile_version=version
        )
        analysis = persistence.analysis_to_api(cached) if cached else None
    analysis = analysis or {"matched_skills": [], "missing_skills": []}

    if user is not None and background:
        task = await tasks.enqueue(
            user.id,
            "optimise",
            {"profile": profile, "job_description": description, "analysis": analysis},
        )
        return {"status": "queued", "task_id": task.id}

    try:
        result = await optimizer.propose_optimisations(profile, description, analysis)
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "optimise")
    except Exception as exc:
        raise errors.unexpected(exc, "optimise")

    return {"status": "success", **result}


@router.post("/optimize/apply")
async def apply(
    request: Request,
    payload: ApplyRequest,
    background: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply the accepted edits, re-score against the same posting, and store."""
    ratelimit.check(
        request,
        "inference",
        config.RATE_LIMIT_INFERENCE_PER_HOUR,
        user_id=user.id if user else None,
    )

    if not payload.accepted_ids:
        raise errors.bad_request(
            "no_changes_accepted", "Accept at least one change to build a tailored resume."
        )

    profile, description, profile_id, version = await _resolve(
        db,
        user,
        profile_id=payload.profile_id,
        job_id=payload.job_id,
        inline_profile=payload.profile,
        inline_description=payload.job_description,
    )

    if user is not None and background:
        task = await tasks.enqueue(
            user.id,
            "tailor",
            {
                "profile": profile,
                "job_description": description,
                "changes": payload.changes,
                "accepted_ids": payload.accepted_ids,
                "rejected_changes": payload.rejected_changes,
                "profile_id": profile_id,
                "job_id": payload.job_id,
                "profile_version": version or 1,
                "before_score": payload.before_score,
            },
        )
        return {"status": "queued", "task_id": task.id}

    tailored = optimizer.apply_changes(profile, payload.changes, payload.accepted_ids)

    try:
        after = await analyze_job_match(
            resume_profile=tailored, job_description=description
        )
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "ats")
    except Exception as exc:
        raise errors.unexpected(exc, "ats")

    record_id = None
    if profile_id is not None and payload.job_id is not None:
        record_id = await _store(
            db,
            profile_id=profile_id,
            job_id=payload.job_id,
            profile_version=version or 1,
            tailored=tailored,
            changes=payload.changes,
            accepted_ids=payload.accepted_ids,
            rejected=payload.rejected_changes,
            before_score=payload.before_score,
            after_score=after["match_score"],
        )

    return {
        "status": "success",
        "tailored_profile": tailored,
        "after_analysis": after,
        "before_score": payload.before_score,
        "after_score": after["match_score"],
        "tailored_resume_id": record_id,
    }


def _pdf_response(
    profile: dict[str, Any], filename: str, template: str | None = None
) -> Response:
    content = resume_pdf.render(profile, template)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _filename(profile: dict[str, Any]) -> str:
    name = "".join(
        char for char in str(profile.get("name") or "resume") if char.isalnum() or char in " -_"
    ).strip()
    return f"{(name or 'resume').replace(' ', '-')}-tailored.pdf"


@router.post("/optimize/pdf")
async def render_pdf(payload: RenderRequest):
    """Render any profile to an ATS-safe PDF. Used by guests, who store nothing."""
    if not payload.profile:
        raise errors.bad_request("missing_profile", "A resume profile is required.")
    return _pdf_response(payload.profile, _filename(payload.profile), payload.template)


@router.get("/tailored-resumes")
async def list_tailored(
    job_id: int | None = Query(default=None),
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every tailored resume this account has produced, newest first."""
    query = (
        select(TailoredResume)
        .join(persistence.Profile, persistence.Profile.id == TailoredResume.profile_id)
        .where(persistence.Profile.user_id == user.id)
        .order_by(TailoredResume.created_at.desc())
    )
    if job_id is not None:
        query = query.where(TailoredResume.job_id == job_id)

    rows = list((await db.execute(query)).scalars())
    return {
        "status": "success",
        "tailored_resumes": [
            {
                "id": row.id,
                "job_id": row.job_id,
                "profile_id": row.profile_id,
                "profile_version": row.profile_version,
                "before_score": row.before_score,
                "after_score": row.after_score,
                "accepted_count": len(row.accepted_ids or []),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


async def _owned_tailored(
    db: AsyncSession, tailored_id: int, user_id: int
) -> TailoredResume | None:
    result = await db.execute(
        select(TailoredResume)
        .join(persistence.Profile, persistence.Profile.id == TailoredResume.profile_id)
        .where(TailoredResume.id == tailored_id, persistence.Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.get("/tailored-resumes/{tailored_id}")
async def get_tailored(
    tailored_id: int,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_tailored(db, tailored_id, user.id)
    if row is None:
        raise auth.forbidden()
    return {
        "status": "success",
        "tailored_resume": {
            "id": row.id,
            "job_id": row.job_id,
            "profile_version": row.profile_version,
            "tailored_profile": row.tailored_profile,
            "changes": row.changes,
            "accepted_ids": row.accepted_ids,
            "rejected_changes": row.rejected_changes,
            "before_score": row.before_score,
            "after_score": row.after_score,
        },
    }


@router.get("/templates")
async def list_templates():
    """
    The resume templates on offer.

    They differ in density and ornament only. Single column, base-14 fonts, no
    images and standard headings are not choices - those are the things a
    parser depends on.
    """
    return {
        "status": "success",
        "default": resume_pdf.DEFAULT_TEMPLATE,
        "templates": [
            {"key": style.key, "label": style.label, "description": style.description}
            for style in resume_pdf.TEMPLATES.values()
        ],
    }


@router.get("/tailored-resumes/{tailored_id}/pdf")
async def download_tailored(
    tailored_id: int,
    template: str | None = Query(default=None),
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_tailored(db, tailored_id, user.id)
    if row is None:
        raise auth.forbidden()
    return _pdf_response(row.tailored_profile, _filename(row.tailored_profile), template)
