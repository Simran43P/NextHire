"""
The application tracker.

Everything upstream of this produces a decision - is this job worth applying
to. This is where the decisions go once they are made, so that "did I apply to
that one?" and "who owes me a reply?" have answers.

A tracked application keeps the match score and the tailored resume that was
sent, because three weeks later the useful question is not what the posting
said but what *you* said to it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import errors
from db import get_db
from models import (
    Application,
    ApplicationStatus,
    AtsAnalysis,
    Job,
    JobSearch,
    Profile,
    TailoredResume,
    User,
    utcnow,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])

# The order a board reads in, left to right.
BOARD_ORDER = [
    ApplicationStatus.SAVED,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
]

# Statuses that mean the employer came back, whatever the answer.
_RESPONDED = {
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
}


class CreateApplication(BaseModel):
    job_id: int
    status: ApplicationStatus = ApplicationStatus.SAVED
    tailored_resume_id: int | None = None
    notes: str = ""


class UpdateApplication(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = None
    follow_up_on: datetime | None = None
    tailored_resume_id: int | None = None


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; compare everything in UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _owned_job(db: AsyncSession, job_id: int, user_id: int) -> Job | None:
    result = await db.execute(
        select(Job)
        .join(JobSearch, JobSearch.id == Job.search_id)
        .join(Profile, Profile.id == JobSearch.profile_id)
        .where(Job.id == job_id, Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _owned_application(
    db: AsyncSession, application_id: int, user_id: int
) -> Application | None:
    result = await db.execute(
        select(Application).where(
            Application.id == application_id, Application.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _decorate(
    db: AsyncSession, applications: list[Application], user_id: int
) -> list[dict[str, Any]]:
    """Attach the posting, the best known match score, and the resume sent."""
    if not applications:
        return []

    job_ids = [row.job_id for row in applications]

    jobs = {
        job.id: job
        for job in (await db.execute(select(Job).where(Job.id.in_(job_ids)))).scalars()
    }

    # Best score seen for each job across this user's profiles. "Best" rather
    # than "latest" because a corrected profile creates a second analysis and
    # the higher one is the one the candidate acted on.
    scores: dict[int, int] = {}
    analyses = (
        await db.execute(
            select(AtsAnalysis)
            .join(Profile, Profile.id == AtsAnalysis.profile_id)
            .where(AtsAnalysis.job_id.in_(job_ids), Profile.user_id == user_id)
        )
    ).scalars()
    for analysis in analyses:
        current = scores.get(analysis.job_id)
        if current is None or analysis.match_score > current:
            scores[analysis.job_id] = analysis.match_score

    tailored_ids = [row.tailored_resume_id for row in applications if row.tailored_resume_id]
    tailored = {
        row.id: row
        for row in (
            await db.execute(select(TailoredResume).where(TailoredResume.id.in_(tailored_ids)))
        ).scalars()
    } if tailored_ids else {}

    decorated = []
    for row in applications:
        job = jobs.get(row.job_id)
        resume = tailored.get(row.tailored_resume_id) if row.tailored_resume_id else None
        decorated.append(
            {
                "id": row.id,
                "job_id": row.job_id,
                "status": row.status.value,
                "notes": row.notes,
                "applied_at": row.applied_at.isoformat() if row.applied_at else None,
                "follow_up_on": row.follow_up_on.isoformat() if row.follow_up_on else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "match_score": scores.get(row.job_id),
                "tailored_resume_id": row.tailored_resume_id,
                "tailored_after_score": resume.after_score if resume else None,
                "title": job.title if job else "",
                "company": job.company if job else "",
                "location": job.location if job else "",
                "apply_link": job.apply_link if job else None,
                "is_remote": job.is_remote if job else False,
            }
        )
    return decorated


def _stats(applications: list[Application]) -> dict[str, Any]:
    """
    The four numbers worth seeing above a board.

    Response rate counts only applications that were actually sent: leaving
    saved-but-not-applied rows in the denominator would make a careful
    shortlist look like rejection.
    """
    now = utcnow()
    week_ago = now - timedelta(days=7)

    counts = {status.value: 0 for status in BOARD_ORDER}
    for row in applications:
        counts[row.status.value] += 1

    sent = [row for row in applications if row.status is not ApplicationStatus.SAVED]
    responded = [row for row in sent if row.status in _RESPONDED]

    applied_this_week = sum(
        1
        for row in sent
        if (applied := _aware(row.applied_at)) is not None and applied >= week_ago
    )
    awaiting = sum(1 for row in sent if row.status is ApplicationStatus.APPLIED)

    overdue = sum(
        1
        for row in applications
        if (due := _aware(row.follow_up_on)) is not None
        and due <= now
        and row.status is not ApplicationStatus.REJECTED
    )

    return {
        "total": len(applications),
        "counts": counts,
        "applied_this_week": applied_this_week,
        "awaiting_response": awaiting,
        "response_rate": round(100 * len(responded) / len(sent)) if sent else None,
        "follow_ups_due": overdue,
    }


@router.get("")
async def board(
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every tracked application, grouped into board columns, with summary counts."""
    rows = list(
        (
            await db.execute(
                select(Application)
                .where(Application.user_id == user.id)
                .order_by(Application.created_at.desc())
            )
        ).scalars()
    )

    decorated = await _decorate(db, rows, user.id)
    columns: dict[str, list[dict[str, Any]]] = {status.value: [] for status in BOARD_ORDER}
    for item in decorated:
        columns[item["status"]].append(item)

    return {
        "status": "success",
        "columns": columns,
        "order": [status.value for status in BOARD_ORDER],
        "stats": _stats(rows),
    }


@router.post("", status_code=201)
async def track(
    payload: CreateApplication,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start tracking a posting.

    Tracking the same job twice returns the existing row rather than creating a
    duplicate - clicking save twice is a slip, not an instruction.
    """
    if await _owned_job(db, payload.job_id, user.id) is None:
        raise auth.forbidden()

    existing = (
        await db.execute(
            select(Application).where(
                Application.user_id == user.id, Application.job_id == payload.job_id
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        decorated = await _decorate(db, [existing], user.id)
        return {"status": "success", "application": decorated[0], "already_tracked": True}

    row = Application(
        user_id=user.id,
        job_id=payload.job_id,
        status=payload.status,
        notes=payload.notes.strip(),
        tailored_resume_id=payload.tailored_resume_id,
        applied_at=utcnow() if payload.status is not ApplicationStatus.SAVED else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    decorated = await _decorate(db, [row], user.id)
    return {"status": "success", "application": decorated[0], "already_tracked": False}


@router.patch("/{application_id}")
async def update(
    application_id: int,
    payload: UpdateApplication,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_application(db, application_id, user.id)
    if row is None:
        raise auth.forbidden()

    if payload.status is not None:
        # Moving out of SAVED for the first time is the moment it was applied,
        # and that date is what every follow-up question hangs off.
        if row.status is ApplicationStatus.SAVED and payload.status is not ApplicationStatus.SAVED:
            row.applied_at = row.applied_at or utcnow()
        if payload.status is ApplicationStatus.SAVED:
            row.applied_at = None
        row.status = payload.status

    if payload.notes is not None:
        row.notes = payload.notes.strip()
    if payload.follow_up_on is not None:
        row.follow_up_on = payload.follow_up_on
    if payload.tailored_resume_id is not None:
        row.tailored_resume_id = payload.tailored_resume_id

    await db.commit()
    await db.refresh(row)

    decorated = await _decorate(db, [row], user.id)
    return {"status": "success", "application": decorated[0]}


@router.delete("/{application_id}")
async def untrack(
    application_id: int,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_application(db, application_id, user.id)
    if row is None:
        raise auth.forbidden()

    await db.delete(row)
    await db.commit()
    return {"status": "success"}
