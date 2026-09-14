"""
NextHire API.

Four stages, one endpoint each:

    POST /api/parse-resume   PDF        -> structured profile
    POST /api/infer-titles   profile    -> ranked job titles
    POST /api/jobs           titles     -> live postings (keyword pre-scored)
    POST /api/analyze-ats    profile+JD -> ATS match analysis

Every model failure reaches the client as a real HTTP error with a machine-
readable code, never as an empty or zero-valued success. The client depends on
being able to tell "this went wrong" from "this is your actual result".
"""

import contextlib
import traceback
from typing import Any

import pymupdf
from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
import llm
import prescore
from ats_matcher import analyze_job_match
from extractor import extract_resume_data
from infer_titles import infer_job_titles, to_api_shape
from job_search import search_all_jobs


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[startup] NextHire API | {config.describe()}")
    if config.USE_MOCK_JOBS and config.RAPIDAPI_KEY is None:
        print("[startup] No RAPIDAPI_KEY set - job search will serve sample postings.")
    yield
    await llm.close_client()


app = FastAPI(
    title="NextHire Core API",
    description="Backend services for the Job Application AI Agent",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class JobSearchRequest(BaseModel):
    job_titles: list[dict[str, Any]] = Field(default_factory=list)
    # Optional: supplying the profile lets every posting be annotated with the
    # candidate's own skills that appear in it, for free and without a model call.
    resume_profile: dict[str, Any] | None = None


class AtsRequest(BaseModel):
    resume_profile: dict[str, Any]
    job_description: str


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def _llm_error(exc: llm.LLMError, stage: str) -> HTTPException:
    """Turn a typed model failure into an HTTP error the client can act on."""
    print(f"[error] {stage}: {exc.code} - {exc.detail}")
    return HTTPException(
        status_code=exc.http_status,
        detail={
            "code": exc.code,
            "message": exc.message,
            "stage": stage,
            "retryable": True,
        },
    )


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": code, "message": message, "retryable": False},
    )


def _unexpected(exc: Exception, stage: str) -> HTTPException:
    print(f"\n========== UNEXPECTED ERROR ({stage}) ==========")
    traceback.print_exc()
    print("================================================\n")
    return HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "message": "Something went wrong on our side. Please try again.",
            "stage": stage,
            "retryable": True,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {
        "message": "NextHire API is running!",
        "jobs_mode": "mock" if config.USE_MOCK_JOBS else "live",
        "model": config.OLLAMA_MODEL,
    }


@app.get("/api/health")
async def health():
    """Cheap readiness probe the UI can use to warn before a long upload fails."""
    return {
        "status": "ok",
        "jobs_mode": "mock" if config.USE_MOCK_JOBS else "live",
        "model": config.OLLAMA_MODEL,
        "max_upload_mb": config.MAX_UPLOAD_MB,
    }


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
            raise _bad_request(
                "file_too_large",
                f"That file is larger than {config.MAX_UPLOAD_MB}MB. "
                "Please upload a smaller PDF.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF and turn it into a structured profile."""
    content = await _read_upload_within_limit(file)

    if not content:
        raise _bad_request("empty_file", "That file is empty.")

    # Validate by content, not by filename. An extension proves nothing.
    if not content.startswith(b"%PDF-"):
        raise _bad_request(
            "not_a_pdf",
            "That does not look like a PDF file. Only PDF resumes are supported.",
        )

    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            pages = [document.load_page(i).get_text("text") for i in range(len(document))]
        extracted_text = "\n".join(pages).strip()
    except Exception as exc:
        print(f"[parse] could not read PDF: {exc}")
        raise _bad_request(
            "unreadable_pdf",
            "This PDF could not be read. It may be corrupted or password protected.",
        )

    # A scanned or image-only resume extracts to almost nothing. Sending that to
    # the model produces a confidently empty profile, which is worse than an error.
    if len(extracted_text) < config.MIN_RESUME_CHARS:
        raise _bad_request(
            "no_text_in_pdf",
            "No readable text was found in this PDF. It looks like a scan or an "
            "image. Please upload a text-based PDF resume.",
        )

    try:
        result = await extract_resume_data(extracted_text)
    except llm.LLMError as exc:
        raise _llm_error(exc, "extraction")
    except Exception as exc:
        raise _unexpected(exc, "extraction")

    return {
        "status": "success",
        "filename": file.filename,
        "profile": result["profile"],
        "gaps": result["gaps"],
        "raw_text": extracted_text,
        "message": "Resume parsed successfully.",
    }


@app.post("/api/infer-titles")
async def api_infer_titles(profile: dict = Body(...)):
    """Infer the job titles a profile actually qualifies for."""
    if not profile:
        raise _bad_request("missing_profile", "A resume profile is required.")

    try:
        titles = await infer_job_titles(profile)
    except llm.LLMError as exc:
        raise _llm_error(exc, "inference")
    except Exception as exc:
        raise _unexpected(exc, "inference")

    return {"status": "success", "titles": to_api_shape(titles)}


@app.post("/api/jobs")
async def api_search_jobs(
    request: JobSearchRequest,
    country: str = Query(default=None),
):
    """Search live postings for the selected titles."""
    if not request.job_titles:
        raise _bad_request("no_titles", "Select at least one job title to search.")

    try:
        result = await search_all_jobs(request.job_titles, country)
    except Exception as exc:
        raise _unexpected(exc, "job_search")

    jobs = prescore.annotate_jobs(request.resume_profile, result["jobs"])

    return {
        "status": "success",
        "jobs": jobs,
        "warnings": result["warnings"],
        "used_mock": result["used_mock"],
        "quota_exhausted": result["quota_exhausted"],
    }


@app.post("/api/analyze-ats")
async def api_analyze_ats(request: AtsRequest):
    """
    Score one resume profile against one job description.

    Failures are HTTP errors, never a zero score. The client fires one request
    per selected job in parallel; the model-side semaphore bounds how many
    actually run at once.
    """
    if not request.resume_profile:
        raise _bad_request("missing_profile", "A resume profile is required.")
    if not request.job_description.strip():
        raise _bad_request(
            "missing_job_description",
            "This posting has no description, so it cannot be analysed.",
        )

    try:
        analysis = await analyze_job_match(
            resume_profile=request.resume_profile,
            job_description=request.job_description,
        )
    except llm.LLMError as exc:
        raise _llm_error(exc, "ats")
    except Exception as exc:
        raise _unexpected(exc, "ats")

    return {"status": "success", "analysis": analysis}
