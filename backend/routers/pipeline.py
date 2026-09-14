"""
The four pipeline stages.

Each endpoint serves two audiences from one code path:

- **A guest** gets the result back directly and nothing is stored. Registration
  is what makes results persist, not what makes them possible.
- **A signed-in user** additionally gets their work saved, cached, and - when
  they ask for `background=true` - run as a tracked task they can navigate away
  from and come back to.

Ownership is enforced in the query, never after the fetch.
"""

from __future__ import annotations

from typing import Any


from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import config
import documents
import errors
import llm
import persistence
import prescore
import ratelimit
import storage
import tasks
from ats_matcher import analyze_job_match
from db import get_db, get_sessionmaker
from extractor import extract_resume_data
from infer_titles import infer_job_titles, to_api_shape
from job_search import search_all_jobs
from models import User

router = APIRouter(prefix="/api", tags=["pipeline"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class InferTitlesRequest(BaseModel):
    # A guest sends the profile itself; a signed-in user may send only its id.
    profile: dict[str, Any] | None = None
    profile_id: int | None = None


class JobSearchRequest(BaseModel):
    job_titles: list[dict[str, Any]] = Field(default_factory=list)
    resume_profile: dict[str, Any] | None = None
    profile_id: int | None = None


class AtsRequest(BaseModel):
    resume_profile: dict[str, Any] | None = None
    job_description: str | None = None
    profile_id: int | None = None
    job_id: int | None = None


class ProfileUpdateRequest(BaseModel):
    profile: dict[str, Any]


# ---------------------------------------------------------------------------
# Background task handlers
# ---------------------------------------------------------------------------


@tasks.register("extraction")
async def _run_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    result = await extract_resume_data(payload["raw_text"])
    async with get_sessionmaker()() as db:
        profile = await persistence.save_resume_and_profile(
            db,
            user_id=payload["user_id"],
            filename=payload.get("filename", ""),
            storage_key=payload.get("storage_key", ""),
            raw_text=payload["raw_text"],
            profile_data=result["profile"],
            gaps=result["gaps"],
            model=config.OLLAMA_MODEL,
        )
    return {
        "profile": result["profile"],
        "gaps": result["gaps"],
        "profile_id": profile.id,
        "profile_version": profile.version,
    }


@tasks.register("inference")
async def _run_inference(payload: dict[str, Any]) -> dict[str, Any]:
    titles = to_api_shape(await infer_job_titles(payload["profile"]))
    profile_id = payload.get("profile_id")
    if profile_id:
        async with get_sessionmaker()() as db:
            await persistence.save_inferred_titles(db, profile_id, titles)
    return {"titles": titles}


@tasks.register("ats")
async def _run_ats(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = await analyze_job_match(
        resume_profile=payload["profile"],
        job_description=payload["job_description"],
    )
    profile_id, job_id = payload.get("profile_id"), payload.get("job_id")
    if profile_id and job_id:
        async with get_sessionmaker()() as db:
            await persistence.save_analysis(
                db,
                profile_id=profile_id,
                job_id=job_id,
                profile_version=payload["profile_version"],
                analysis=analysis,
                model=config.OLLAMA_MODEL,
            )
    return {"analysis": analysis}


# ---------------------------------------------------------------------------
# Stage 1: parse-resume
# ---------------------------------------------------------------------------


async def _read_upload_within_limit(file: UploadFile) -> bytes:
    """
    Read an upload, aborting as soon as it exceeds the configured ceiling.

    Streamed in chunks rather than read whole, so an oversized file is rejected
    without first being pulled entirely into memory.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            raise errors.bad_request(
                "file_too_large",
                f"That file is larger than {config.MAX_UPLOAD_MB}MB. "
                "Please upload a smaller PDF.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_text(content: bytes) -> tuple[str, str]:
    """Pull text out of a PDF or DOCX, or explain why it could not be done."""
    try:
        return documents.extract_text(content)
    except documents.UnsupportedDocument:
        raise errors.bad_request(
            "unsupported_format",
            "That does not look like a PDF or Word document. "
            "Only PDF and DOCX resumes are supported.",
        )
    except documents.UnreadableDocument as exc:
        print(f"[parse] could not read document: {exc}")
        raise errors.bad_request(
            "unreadable_document",
            "This file could not be read. It may be corrupted or password protected.",
        )


@router.post("/parse-resume")
async def parse_resume(
    request: Request,
    file: UploadFile = File(...),
    background: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract text from an uploaded PDF or DOCX and turn it into a structured profile."""
    ratelimit.check(
        request,
        "upload",
        config.RATE_LIMIT_UPLOAD_PER_HOUR,
        user_id=user.id if user else None,
    )

    content = await _read_upload_within_limit(file)

    if not content:
        raise errors.bad_request("empty_file", "That file is empty.")

    # Format is decided by the bytes, never by the filename. An extension is
    # attacker-controlled input and proves nothing about what the file is.
    extracted_text, kind = _extract_text(content)

    # A scanned or image-only resume extracts to almost nothing. Sending that to
    # the model produces a confidently empty profile, which is worse than an error.
    if len(extracted_text) < config.MIN_RESUME_CHARS:
        raise errors.bad_request(
            "no_text_in_document",
            "No readable text was found in this file. "
            + (
                "It looks like a scan or an image. Please upload a text-based PDF."
                if kind == "pdf"
                else "The document appears to be empty."
            ),
        )

    storage_key = ""
    if user is not None:
        storage_key = await storage.save_resume(
            user.id, content, ".docx" if kind == "docx" else ".pdf"
        )

    if user is not None and background:
        task = await tasks.enqueue(
            user.id,
            "extraction",
            {
                "user_id": user.id,
                "raw_text": extracted_text,
                "filename": file.filename or "",
                "storage_key": storage_key,
            },
        )
        return {"status": "queued", "task_id": task.id}

    try:
        result = await extract_resume_data(extracted_text)
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "extraction")
    except Exception as exc:
        raise errors.unexpected(exc, "extraction")

    profile_id = profile_version = None
    if user is not None:
        profile = await persistence.save_resume_and_profile(
            db,
            user_id=user.id,
            filename=file.filename or "",
            storage_key=storage_key,
            raw_text=extracted_text,
            profile_data=result["profile"],
            gaps=result["gaps"],
            model=config.OLLAMA_MODEL,
        )
        profile_id, profile_version = profile.id, profile.version

    return {
        "status": "success",
        "filename": file.filename,
        "profile": result["profile"],
        "gaps": result["gaps"],
        "profile_id": profile_id,
        "profile_version": profile_version,
        "raw_text": extracted_text,
        "message": "Resume parsed successfully.",
    }


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


async def _load_profile_data(
    db: AsyncSession,
    user: User | None,
    profile_id: int | None,
    inline: dict[str, Any] | None,
) -> tuple[dict[str, Any], int | None, int | None]:
    """
    Resolve a profile from either an id (signed in) or an inline body (guest).

    Returns (data, profile_id, profile_version).
    """
    if profile_id is not None:
        if user is None:
            raise auth.forbidden()
        profile = await persistence.get_profile(db, profile_id, user.id)
        if profile is None:
            raise auth.forbidden()
        return profile.data, profile.id, profile.version

    if not inline:
        raise errors.bad_request("missing_profile", "A resume profile is required.")
    return inline, None, None


@router.get("/profiles")
async def list_profiles(
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    profiles = await persistence.list_profiles(db, user.id)
    return {
        "status": "success",
        "profiles": [
            {
                "id": profile.id,
                "version": profile.version,
                "gaps": profile.gaps,
                "name": (profile.data or {}).get("name", ""),
                "skill_count": len((profile.data or {}).get("skills", []) or []),
                "created_at": profile.created_at.isoformat()
                if profile.created_at
                else None,
            }
            for profile in profiles
        ],
    }


@router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: int,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await persistence.get_profile(db, profile_id, user.id)
    if profile is None:
        raise auth.forbidden()
    return {
        "status": "success",
        "profile": profile.data,
        "profile_id": profile.id,
        "profile_version": profile.version,
        "gaps": profile.gaps,
    }


@router.patch("/profiles/{profile_id}")
async def update_profile(
    profile_id: int,
    payload: ProfileUpdateRequest,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save a corrected profile.

    The version bump invalidates every cached analysis for this profile, so a
    correction can never leave stale scores on screen.
    """
    profile = await persistence.get_profile(db, profile_id, user.id)
    if profile is None:
        raise auth.forbidden()

    updated = await persistence.update_profile(db, profile, payload.profile)
    return {
        "status": "success",
        "profile": updated.data,
        "profile_id": updated.id,
        "profile_version": updated.version,
    }


@router.get("/profiles/{profile_id}/resume")
async def download_resume(
    profile_id: int,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve the original PDF, only to the account that uploaded it."""
    from fastapi.responses import Response as FileResponse

    resume = await persistence.get_resume_for_profile(db, profile_id, user.id)
    if resume is None or not resume.storage_key:
        raise errors.not_found("No stored file for that profile.")

    content = await storage.read_resume(resume.storage_key)
    if content is None:
        raise errors.not_found("That file is no longer on disk.")

    is_docx = (resume.storage_key or "").endswith(".docx")
    filename = resume.original_filename or ("resume.docx" if is_docx else "resume.pdf")
    return FileResponse(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if is_docx
            else "application/pdf"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Stage 2: infer-titles
# ---------------------------------------------------------------------------


@router.post("/infer-titles")
async def api_infer_titles(
    request: Request,
    payload: InferTitlesRequest,
    background: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    ratelimit.check(
        request,
        "inference",
        config.RATE_LIMIT_INFERENCE_PER_HOUR,
        user_id=user.id if user else None,
    )

    data, profile_id, _ = await _load_profile_data(
        db, user, payload.profile_id, payload.profile
    )

    if user is not None and background:
        task = await tasks.enqueue(
            user.id, "inference", {"profile": data, "profile_id": profile_id}
        )
        return {"status": "queued", "task_id": task.id}

    try:
        titles = to_api_shape(await infer_job_titles(data))
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "inference")
    except Exception as exc:
        raise errors.unexpected(exc, "inference")

    if profile_id is not None:
        await persistence.save_inferred_titles(db, profile_id, titles)

    return {"status": "success", "titles": titles}


# ---------------------------------------------------------------------------
# Stage 3: job search
# ---------------------------------------------------------------------------


@router.post("/jobs")
async def api_search_jobs(
    payload: JobSearchRequest,
    country: str = Query(default=None),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.job_titles:
        raise errors.bad_request("no_titles", "Select at least one job title to search.")

    profile_data = payload.resume_profile
    profile_id = None
    if payload.profile_id is not None:
        profile_data, profile_id, _ = await _load_profile_data(
            db, user, payload.profile_id, payload.resume_profile
        )

    try:
        result = await search_all_jobs(payload.job_titles, country)
    except Exception as exc:
        raise errors.unexpected(exc, "job_search")

    jobs = prescore.annotate_jobs(profile_data, result["jobs"])

    search_id = None
    if profile_id is not None:
        await persistence.mark_titles_selected(
            db, profile_id, [entry.get("title", "") for entry in payload.job_titles]
        )
        search, rows = await persistence.save_search(
            db,
            profile_id=profile_id,
            titles=payload.job_titles,
            country=country or config.DEFAULT_COUNTRY,
            jobs=jobs,
            warnings=result["warnings"],
            used_mock=result["used_mock"],
        )
        search_id = search.id
        # Return the stored rows so every posting carries its database id, which
        # is what makes analysis caching possible on the next stage.
        jobs = [persistence.job_to_api(row) for row in rows]

    return {
        "status": "success",
        "jobs": jobs,
        "search_id": search_id,
        "warnings": result["warnings"],
        "used_mock": result["used_mock"],
        "quota_exhausted": result["quota_exhausted"],
    }


# ---------------------------------------------------------------------------
# Stage 4: ATS analysis
# ---------------------------------------------------------------------------


@router.post("/analyze-ats")
async def api_analyze_ats(
    request: Request,
    payload: AtsRequest,
    background: bool = Query(default=False),
    refresh: bool = Query(default=False),
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Score one resume profile against one job description.

    Failures are HTTP errors, never a zero score. For a signed-in user the
    result is cached against the profile's current version, so re-opening a job
    does not re-run a 30-second inference - and correcting the profile bumps
    that version, which invalidates the cache rather than showing stale numbers.
    """
    ratelimit.check(
        request,
        "inference",
        config.RATE_LIMIT_INFERENCE_PER_HOUR,
        user_id=user.id if user else None,
    )

    data, profile_id, profile_version = await _load_profile_data(
        db, user, payload.profile_id, payload.resume_profile
    )

    description = payload.job_description
    job_id = payload.job_id
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
            "This posting has no description, so it cannot be analysed.",
        )

    cacheable = profile_id is not None and job_id is not None
    if cacheable and not refresh:
        cached = await persistence.find_cached_analysis(
            db, profile_id=profile_id, job_id=job_id, profile_version=profile_version
        )
        if cached is not None:
            return {"status": "success", "analysis": persistence.analysis_to_api(cached)}

    if user is not None and background:
        task = await tasks.enqueue(
            user.id,
            "ats",
            {
                "profile": data,
                "job_description": description,
                "profile_id": profile_id,
                "job_id": job_id,
                "profile_version": profile_version,
            },
        )
        return {"status": "queued", "task_id": task.id}

    try:
        analysis = await analyze_job_match(
            resume_profile=data, job_description=description
        )
    except llm.LLMError as exc:
        raise errors.llm_error(exc, "ats")
    except Exception as exc:
        raise errors.unexpected(exc, "ats")

    if cacheable:
        await persistence.save_analysis(
            db,
            profile_id=profile_id,
            job_id=job_id,
            profile_version=profile_version,
            analysis=analysis,
            model=config.OLLAMA_MODEL,
        )

    return {"status": "success", "analysis": analysis}
