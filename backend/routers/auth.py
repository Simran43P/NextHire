"""
Registration, sign-in, sign-out, and password reset.

The guest-to-account carryover lives here too: a visitor completes the pipeline
without an account, then registers, and the work they just did follows them in
rather than being thrown away.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import config
import errors
import mailer
import persistence
import ratelimit
from db import get_db
from models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Carryover(BaseModel):
    """Work a guest did before registering."""

    profile: dict[str, Any] | None = None
    gaps: list[str] = Field(default_factory=list)
    raw_text: str = ""
    filename: str = ""


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = ""
    carryover: Carryover | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


def _public_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def _find_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


@router.post("/register", status_code=201)
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    ratelimit.check(request, "auth", config.RATE_LIMIT_AUTH_PER_HOUR)

    email = auth.normalise_email(payload.email)
    problem = auth.password_problem(payload.password)
    if problem:
        raise errors.bad_request("weak_password", problem)

    if await _find_by_email(db, email) is not None:
        raise errors.conflict(
            "email_taken", "An account with that email already exists."
        )

    user = User(
        email=email,
        password_hash=auth.hash_password(payload.password),
        display_name=payload.display_name.strip()[:120],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Carry the guest's work into the new account. Losing it here is the whole
    # reason people abandon a sign-up they were otherwise happy to complete.
    carried: dict[str, Any] | None = None
    if payload.carryover and payload.carryover.profile:
        profile = await persistence.save_resume_and_profile(
            db,
            user_id=user.id,
            filename=payload.carryover.filename,
            storage_key="",  # no file survives a guest session, only the text
            raw_text=payload.carryover.raw_text,
            profile_data=payload.carryover.profile,
            gaps=payload.carryover.gaps,
            model=config.OLLAMA_MODEL,
        )
        carried = {"profile_id": profile.id, "version": profile.version}
        print(f"[auth] carried a guest profile into new account {user.id}")

    token = await auth.create_session(db, user)
    auth.set_session_cookie(response, token)
    return {"status": "success", "user": _public_user(user), "carried": carried}


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    ratelimit.check(request, "auth", config.RATE_LIMIT_AUTH_PER_HOUR)

    email = auth.normalise_email(payload.email)
    user = await _find_by_email(db, email)

    # One message for both "no such account" and "wrong password". Telling them
    # apart hands an attacker a list of which emails are registered.
    if user is None or not auth.verify_password(user.password_hash, payload.password):
        raise errors.bad_request(
            "invalid_credentials", "That email or password is not right."
        )

    # Transparently upgrade a hash made with older Argon2 parameters.
    if auth.needs_rehash(user.password_hash):
        user.password_hash = auth.hash_password(payload.password)
        await db.commit()

    token = await auth.create_session(db, user)
    auth.set_session_cookie(response, token)
    return {"status": "success", "user": _public_user(user)}


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await auth.destroy_session(db, request.cookies.get(config.SESSION_COOKIE_NAME))
    auth.clear_session_cookie(response)
    return {"status": "success"}


@router.get("/me")
async def me(
    user: User | None = Depends(auth.optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Who is signed in, if anyone.

    Returns 200 with `user: null` for a guest rather than 401, because "nobody
    is signed in" is a normal answer to this question, not a failure.
    """
    if user is None:
        return {"status": "success", "user": None}
    return {
        "status": "success",
        "user": _public_user(user),
        "profile_count": await persistence.count_profiles(db, user.id),
    }


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Begin a password reset.

    Always reports success, whether or not the address is registered - the
    response must not reveal which emails have accounts.
    """
    ratelimit.check(request, "auth", config.RATE_LIMIT_AUTH_PER_HOUR)

    user = await _find_by_email(db, auth.normalise_email(payload.email))
    if user is not None:
        token = await auth.create_password_reset(db, user)
        await mailer.send_password_reset(user.email, token)

    return {
        "status": "success",
        "message": (
            "If that email has an account, a reset link is on its way. "
            f"It expires in {config.PASSWORD_RESET_TTL_MINUTES} minutes."
        ),
    }


@router.post("/reset-password")
async def reset_password(
    request: Request,
    response: Response,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    ratelimit.check(request, "auth", config.RATE_LIMIT_AUTH_PER_HOUR)

    problem = auth.password_problem(payload.password)
    if problem:
        raise errors.bad_request("weak_password", problem)

    user = await auth.consume_password_reset(db, payload.token)
    if user is None:
        raise errors.bad_request(
            "invalid_reset_token",
            "That reset link is invalid, already used, or expired. "
            "Please request a new one.",
        )

    user.password_hash = auth.hash_password(payload.password)
    await db.commit()

    # Every existing session dies with the old password. A reset is often a
    # response to a suspected compromise, and leaving the intruder signed in
    # would defeat the point.
    await auth.destroy_all_sessions(db, user.id)

    token = await auth.create_session(db, user)
    auth.set_session_cookie(response, token)
    return {"status": "success", "user": _public_user(user)}
