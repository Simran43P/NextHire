"""
Passwords, sessions, and the request dependencies that enforce ownership.

Two decisions worth stating:

**Tokens are stored hashed.** A session cookie and a password-reset link are
bearer credentials: whoever holds one is the user. Storing them in plaintext
means a database leak is an immediate account takeover for everyone. Only the
SHA-256 of each token is persisted, so a stolen database yields nothing usable.
SHA-256 rather than Argon2 is right here - these are 256-bit random values, not
guessable secrets, so there is nothing for a slow hash to protect against.

**Passwords use Argon2id.** The current OWASP recommendation, and the library
handles salting and parameter encoding itself.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from db import get_db
from models import PasswordReset, Session, User, utcnow

_hasher = PasswordHasher()

# Sessions are looked up by this many bytes of entropy - far beyond guessing.
_TOKEN_BYTES = 32


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates the current Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


def password_problem(password: str) -> str | None:
    """
    Validate a password, returning the reason it is unacceptable.

    Length is the only rule. Composition requirements ("one uppercase, one
    symbol") measurably push people towards weaker, more predictable passwords,
    and NIST has advised against them for years.
    """
    if len(password) < config.MIN_PASSWORD_LENGTH:
        return (
            f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters."
        )
    if len(password) > 200:
        return "Password must be under 200 characters."
    return None


def normalise_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def _new_token() -> tuple[str, str]:
    """Return (raw token to hand out, hash to store)."""
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


async def create_session(db: AsyncSession, user: User) -> str:
    """Create a session and return the raw token for the cookie."""
    raw, token_hash = _new_token()
    session = Session(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=config.SESSION_TTL_DAYS),
    )
    db.add(session)
    await db.commit()
    return raw


async def resolve_session(db: AsyncSession, raw_token: str | None) -> User | None:
    """Return the signed-in user, or None. Expired sessions are cleaned up."""
    if not raw_token:
        return None

    result = await db.execute(
        select(Session).where(Session.token_hash == hash_token(raw_token))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        # SQLite hands back naive datetimes; compare in UTC regardless.
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= utcnow():
        await db.delete(session)
        await db.commit()
        return None

    user = await db.get(User, session.user_id)
    if user is None:
        return None

    # Cheap activity tracking, written at most once a day to avoid a database
    # write on literally every authenticated request.
    last_seen = session.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if utcnow() - last_seen > timedelta(days=1):
        session.last_seen_at = utcnow()
        await db.commit()

    return user


async def destroy_session(db: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    await db.execute(delete(Session).where(Session.token_hash == hash_token(raw_token)))
    await db.commit()


async def destroy_all_sessions(db: AsyncSession, user_id: int) -> None:
    """Used on password change and account deletion - revocation must be total."""
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.commit()


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


async def create_password_reset(db: AsyncSession, user: User) -> str:
    # Any outstanding reset is invalidated, so only the newest link works.
    await db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    raw, token_hash = _new_token()
    db.add(
        PasswordReset(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=utcnow()
            + timedelta(minutes=config.PASSWORD_RESET_TTL_MINUTES),
        )
    )
    await db.commit()
    return raw


async def consume_password_reset(db: AsyncSession, raw_token: str) -> User | None:
    """
    Redeem a reset token exactly once.

    Returns the user on success, None if the token is unknown, expired, or has
    already been used.
    """
    result = await db.execute(
        select(PasswordReset).where(PasswordReset.token_hash == hash_token(raw_token))
    )
    reset = result.scalar_one_or_none()
    if reset is None or reset.used_at is not None:
        return None

    expires_at = reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= utcnow():
        return None

    user = await db.get(User, reset.user_id)
    if user is None:
        return None

    reset.used_at = utcnow()
    await db.commit()
    return user


# ---------------------------------------------------------------------------
# Request dependencies
# ---------------------------------------------------------------------------


def _session_cookie(request_cookie: str | None) -> str | None:
    return request_cookie


async def optional_user(
    db: AsyncSession = Depends(get_db),
    nexthire_session: str | None = Cookie(default=None, alias=config.SESSION_COOKIE_NAME),
) -> User | None:
    """The signed-in user, or None. Used by endpoints guests may also reach."""
    return await resolve_session(db, nexthire_session)


async def current_user(user: User | None = Depends(optional_user)) -> User:
    """The signed-in user, or a 401. Used by everything that touches stored data."""
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "not_authenticated",
                "message": "Please sign in to continue.",
                "retryable": False,
            },
        )
    return user


def forbidden() -> HTTPException:
    """
    Raised when a signed-in user reaches something that is not theirs.

    Deliberately indistinguishable from "does not exist": telling a stranger
    that profile 41 exists but is not theirs is itself a disclosure.
    """
    return HTTPException(
        status_code=404,
        detail={
            "code": "not_found",
            "message": "Not found.",
            "retryable": False,
        },
    )


def set_session_cookie(response, raw_token: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=config.SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(
        key=config.SESSION_COOKIE_NAME,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
    )


__all__ = [
    "clear_session_cookie",
    "consume_password_reset",
    "create_password_reset",
    "create_session",
    "current_user",
    "destroy_all_sessions",
    "destroy_session",
    "forbidden",
    "hash_password",
    "hash_token",
    "needs_rehash",
    "normalise_email",
    "optional_user",
    "password_problem",
    "resolve_session",
    "set_session_cookie",
    "verify_password",
]
