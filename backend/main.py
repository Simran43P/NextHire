"""
NextHire API.

The pipeline, one endpoint per stage:

    POST /api/parse-resume   PDF        -> structured profile
    POST /api/infer-titles   profile    -> ranked job titles
    POST /api/jobs           titles     -> live postings (keyword pre-scored)
    POST /api/analyze-ats    profile+JD -> ATS match analysis
    POST /api/optimize       analysis   -> reviewable tailoring edits
    POST /api/cover-letter   analysis   -> a cover letter, claims located
    POST /api/interview-prep analysis   -> likely interview questions
    GET  /api/skills-gap                -> what is costing you, across postings
    GET  /api/applications              -> the tracker board

Plus accounts (/api/auth), background work (/api/tasks), and data ownership
(/api/account). Guests may run the whole pipeline; signing in is what makes the
results persist.

Every model failure reaches the client as a real HTTP error with a machine-
readable code, never as an empty or zero-valued success. The client depends on
being able to tell "this went wrong" from "this is your actual result".
"""

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
import db as database
import llm
import tasks
from routers import (
    account,
    applications,
    auth as auth_routes,
    optimize,
    pipeline,
    prep,
    tasks as task_routes,
)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[startup] NextHire API | {config.describe()}")
    if config.USE_MOCK_JOBS and config.RAPIDAPI_KEY is None:
        print("[startup] No RAPIDAPI_KEY set - job search will serve sample postings.")

    # Migrations run on startup so the app is always self-consistent - there is
    # no state where the code has moved on and the database has not.
    await database.ensure_schema()
    await tasks.start_workers()

    yield

    await tasks.stop_workers()
    await llm.close_client()
    await database.dispose()


app = FastAPI(
    title="NextHire Core API",
    description="Backend services for the Job Application AI Agent",
    version="2.0.0",
    lifespan=lifespan,
)

# Explicit origins with credentials allowed, because the session cookie has to
# survive the cross-origin hop from the Vite dev server. "*" is not an option:
# browsers reject it alongside credentials, and it would be unsafe regardless.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(pipeline.router)
app.include_router(optimize.router)
app.include_router(prep.router)
app.include_router(applications.router)
app.include_router(task_routes.router)
app.include_router(account.router)


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
        "database": "ok" if await database.healthcheck() else "unavailable",
    }
