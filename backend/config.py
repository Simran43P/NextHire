"""
Central configuration for the NextHire backend.

Every tunable is an environment variable with a working default, so the app
runs locally with no .env at all, and nothing needs editing in source to point
it somewhere else. Previously the Ollama URL, model name, and timeouts were
duplicated as literals across three separate modules.

See .env.example for the full list.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    """Read an integer env var, falling back to the default if unset or junk."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        print(f"[config] {name}={raw!r} is not an integer; using {default}")
        return default


def _bool(name: str, default: bool) -> bool:
    """Read a boolean env var. Accepts 1/true/yes/on, case-insensitive."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated env var into a list of trimmed, non-empty items."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Model serving (Ollama)
# ---------------------------------------------------------------------------

OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# Per-stage timeouts, in seconds. These are ceilings, not targets - the PRD
# targets are lower (60 / 30 / 45). Generous defaults because a 7B model on CPU
# is genuinely slow; lower them on capable hardware.
EXTRACTION_TIMEOUT: int = _int("EXTRACTION_TIMEOUT_SECONDS", 300)
INFERENCE_TIMEOUT: int = _int("INFERENCE_TIMEOUT_SECONDS", 90)
ATS_TIMEOUT: int = _int("ATS_TIMEOUT_SECONDS", 120)

# How many model calls may be in flight at once. A single Ollama instance
# serving one model does not parallelise well, so this is deliberately low.
# It bounds real load while still letting the client fire requests in parallel
# and render each result as it lands.
LLM_CONCURRENCY: int = _int("LLM_CONCURRENCY", 2)

# Context window for extraction. Must stay large enough that multi-page
# resumes are not silently truncated.
EXTRACTION_NUM_CTX: int = _int("EXTRACTION_NUM_CTX", 8192)


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 5)
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

# A PDF that extracts to less than this many characters is almost certainly a
# scan or an image-only export, and must be rejected rather than sent to the
# model as an empty string.
MIN_RESUME_CHARS: int = _int("MIN_RESUME_CHARS", 200)


# ---------------------------------------------------------------------------
# Job search
# ---------------------------------------------------------------------------

RAPIDAPI_KEY: str | None = os.getenv("RAPIDAPI_KEY") or None
RAPIDAPI_HOST: str = os.getenv("RAPIDAPI_HOST", "jsearch.p.rapidapi.com")
JOB_SEARCH_TIMEOUT: int = _int("JOB_SEARCH_TIMEOUT_SECONDS", 60)
DEFAULT_COUNTRY: str = os.getenv("DEFAULT_COUNTRY", "in")

# Serve built-in sample postings instead of calling the aggregator. Set this
# during development to avoid consuming the API quota - each search spends one
# call per selected title. Forced on automatically when no key is configured,
# so the app still works end to end without one.
USE_MOCK_JOBS: bool = _bool("USE_MOCK_JOBS", False) or RAPIDAPI_KEY is None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

# Explicit origins. "*" together with credentials is rejected by browsers and
# unsafe once authentication exists, so it is not an option here.
CORS_ORIGINS: list[str] = _list(
    "CORS_ORIGINS",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

# SQLite by default: no server to run, no cost, and the whole database is one
# file you can copy, inspect, or delete. Point this at Postgres when there is
# ever more than one instance.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./nexthire.db")

# Where uploaded resumes are written. Files are stored under random keys, never
# under their original filename, and are served only through an authorised route.
STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./storage")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "nexthire_session")
SESSION_TTL_DAYS: int = _int("SESSION_TTL_DAYS", 30)

# Leave false for local http development; set true wherever the app is served
# over https, which is everywhere that is not a developer's machine.
COOKIE_SECURE: bool = _bool("COOKIE_SECURE", False)
# "lax" is right when the API and the SPA share a site. Cross-site cookies need
# "none", which browsers only accept alongside Secure.
COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")

PASSWORD_RESET_TTL_MINUTES: int = _int("PASSWORD_RESET_TTL_MINUTES", 30)
MIN_PASSWORD_LENGTH: int = _int("MIN_PASSWORD_LENGTH", 10)


# ---------------------------------------------------------------------------
# Google sign-in (optional)
# ---------------------------------------------------------------------------

# Entirely optional, and off unless both values are present. Creating the
# credentials needs a Google Cloud project, which is free but is something only
# the person deploying this can do - so the app has to work without it rather
# than fail at startup.
GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID") or None
GOOGLE_CLIENT_SECRET: str | None = os.getenv("GOOGLE_CLIENT_SECRET") or None

# Must match a redirect URI registered on the Google credential exactly.
GOOGLE_REDIRECT_URI: str = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
)

GOOGLE_ENABLED: bool = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# In-process counters. Fine for a single instance; a shared store would be
# needed the moment there are two, which is a Phase 5 problem.
RATE_LIMIT_ENABLED: bool = _bool("RATE_LIMIT_ENABLED", True)
# Model calls cost real compute, so they are limited far harder than reads.
RATE_LIMIT_INFERENCE_PER_HOUR: int = _int("RATE_LIMIT_INFERENCE_PER_HOUR", 60)
RATE_LIMIT_UPLOAD_PER_HOUR: int = _int("RATE_LIMIT_UPLOAD_PER_HOUR", 20)
RATE_LIMIT_AUTH_PER_HOUR: int = _int("RATE_LIMIT_AUTH_PER_HOUR", 20)


# ---------------------------------------------------------------------------
# Outbound email (password reset only)
# ---------------------------------------------------------------------------

# Entirely optional. With no host configured, reset links are printed to the
# server log instead of emailed, which is all a single-user local install needs
# and costs nothing.
SMTP_HOST: str | None = os.getenv("SMTP_HOST") or None
SMTP_PORT: int = _int("SMTP_PORT", 587)
SMTP_USER: str | None = os.getenv("SMTP_USER") or None
SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") or None
SMTP_FROM: str = os.getenv("SMTP_FROM", "nexthire@localhost")

# Used to build the link in a reset email.
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:5173")


def describe() -> str:
    """One-line startup summary, so misconfiguration is obvious immediately."""
    jobs_mode = "MOCK (no quota used)" if USE_MOCK_JOBS else "live via RapidAPI"
    google = "on" if GOOGLE_ENABLED else "off"
    return (
        f"model={OLLAMA_MODEL} at {OLLAMA_URL} | "
        f"llm_concurrency={LLM_CONCURRENCY} | "
        f"jobs={jobs_mode} | "
        f"max_upload={MAX_UPLOAD_MB}MB | "
        f"cors={len(CORS_ORIGINS)} origin(s) | "
        f"google sign-in={google}"
    )
