"""
Database schema.

Eleven tables, matching PRD section 6.3. Three principles shape them:

**Derived work is versioned, not overwritten.** `profiles.version` increments on
every re-extraction or manual correction, and cached analyses key on it. A
corrected profile therefore invalidates its stale scores rather than silently
keeping them.

**Postings are a cache, not a job board.** The `jobs` table records what was
shown to the candidate at search time. Listings expire; the stored copy is what
their analysis actually referred to.

**Nothing is hard-deleted except on request.** Account deletion removes the
user's rows and files outright, because a resume is not something to soft-delete.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware UTC. Naive datetimes in a database are a future bug."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    resumes: Mapped[list[Resume]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base, TimestampMixin):
    """
    Server-side sessions rather than self-contained tokens.

    A row can be deleted, which means sign-out and account deletion revoke
    access immediately. A JWT cannot be withdrawn before it expires, and
    "immediately revokes access" is a requirement here (NFR-SEC-9).
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class PasswordReset(Base, TimestampMixin):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class Resume(Base, TimestampMixin):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # Kept so a future model upgrade can re-extract without asking the
    # candidate to upload the same file again.
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="resumes")
    profiles: Mapped[list[Profile]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class Profile(Base, TimestampMixin):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    gaps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    extraction_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # Incremented on every re-extraction or manual correction. Cached analyses
    # key on it, so editing a profile invalidates its stale scores.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    resume: Mapped[Resume] = relationship(back_populates="profiles")


class InferredTitle(Base, TimestampMixin):
    __tablename__ = "inferred_titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class JobSearch(Base, TimestampMixin):
    __tablename__ = "job_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    titles_searched: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="in", nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    jobs: Mapped[list[Job]] = relationship(
        back_populates="search", cascade="all, delete-orphan"
    )


class Job(Base, TimestampMixin):
    """A posting as it appeared at search time, not a live listing."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(
        ForeignKey("job_searches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    company: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(80), default=None)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    apply_link: Mapped[str | None] = mapped_column(String(1000), default=None)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    posted_at: Mapped[str | None] = mapped_column(String(64), default=None)
    salary_min: Mapped[float | None] = mapped_column(Float, default=None)
    salary_max: Mapped[float | None] = mapped_column(Float, default=None)
    keyword_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    search: Mapped[JobSearch] = relationship(back_populates="jobs")

    __table_args__ = (
        UniqueConstraint("search_id", "external_id", name="uq_job_per_search"),
    )


class AtsAnalysis(Base, TimestampMixin):
    __tablename__ = "ats_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Denormalised so a cache lookup does not need to join back to profiles.
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommendations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    corrected_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "profile_id", "job_id", "profile_version", name="uq_analysis_cache_key"
        ),
        Index("ix_analysis_lookup", "profile_id", "profile_version"),
    )


# ---------------------------------------------------------------------------
# Application lifecycle (tables land now; the UI arrives in Phase 4)
# ---------------------------------------------------------------------------


class ApplicationStatus(str, enum.Enum):
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    OFFER = "OFFER"
    REJECTED = "REJECTED"


class TailoredResume(Base, TimestampMixin):
    """
    One tailored resume, plus the record of how it came to be.

    The proposed changes and the accepted subset are both kept. Knowing which
    edits a candidate rejected is what makes a later "before and after" honest,
    and it means a tailored resume can be explained rather than just produced.
    """

    __tablename__ = "tailored_resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Which version of the profile this was tailored from. A later correction
    # does not silently invalidate it, but it does explain a score that no
    # longer matches.
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tailored_profile: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    changes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    accepted_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Suggestions discarded by the fabrication guard, kept so the candidate can
    # see what was thrown out on their behalf.
    rejected_changes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    before_score: Mapped[int | None] = mapped_column(Integer, default=None)
    after_score: Mapped[int | None] = mapped_column(Integer, default=None)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(255), default=None)


class CoverLetter(Base, TimestampMixin):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tone: Mapped[str] = mapped_column(String(40), default="professional", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.SAVED, nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    tailored_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("tailored_resumes.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    follow_up_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped[User] = relationship(back_populates="applications")


# ---------------------------------------------------------------------------
# Background work
# ---------------------------------------------------------------------------


class TaskStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class QueuedTask(Base, TimestampMixin):
    """
    A unit of model work, tracked server-side.

    The point is survivability: extraction can take a minute, and a candidate
    who refreshes or switches tabs mid-way must not lose it. The client polls
    this row rather than holding a request open.
    """

    __tablename__ = "jobs_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.QUEUED, index=True, nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, default=None)
    error: Mapped[dict | None] = mapped_column(JSON, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
