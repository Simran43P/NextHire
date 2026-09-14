"""
Sign in with Google.

Entirely optional. Creating the credentials needs a Google Cloud project, which
is free but is something only the person deploying this can do, so the routes
exist unconditionally and refuse politely when unconfigured. The app works
without it; this is a convenience, not a dependency.

Two details that are easy to get wrong and expensive to get wrong:

**Accounts are matched on the provider's subject id, not on email.** A Google
account can change its address. Matching on email would silently split one
person into two accounts, or - far worse - hand someone else's account to
whoever later acquires that address.

**The state parameter is verified.** Without it the callback accepts a code
from anywhere, which is how CSRF gets you signed into an attacker's account.
"""

from __future__ import annotations

import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import config
import errors
from db import get_db
from models import User

router = APIRouter(prefix="/api/auth/google", tags=["auth"])

AUTHORISE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

STATE_COOKIE = "nexthire_oauth_state"
_STATE_TTL_SECONDS = 600


def _unavailable() -> errors.HTTPException:
    return errors.bad_request(
        "google_not_configured",
        "Google sign-in is not set up on this server. Use an email and password.",
    )


def _frontend(path: str = "/", **params: str) -> str:
    base = config.APP_BASE_URL.rstrip("/")
    if not params:
        return f"{base}{path}"
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{base}{path}?{query}"


@router.get("/status")
async def status():
    """Whether the sign-in button should be shown at all."""
    return {"status": "success", "enabled": config.GOOGLE_ENABLED}


@router.get("/start")
async def start():
    """Send the browser to Google, remembering a state value to check later."""
    if not config.GOOGLE_ENABLED:
        raise _unavailable()

    state = secrets.token_urlsafe(24)
    url = (
        f"{AUTHORISE_URL}"
        f"?client_id={config.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={config.GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        f"&state={state}"
        "&access_type=online"
        "&prompt=select_account"
    )

    response = RedirectResponse(url, status_code=307)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=_STATE_TTL_SECONDS,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return response


async def _exchange(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": config.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("Google did not return an access token.")

        profile_response = await client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        profile_response.raise_for_status()
        return profile_response.json()


async def _find_or_create(db: AsyncSession, info: dict[str, Any]) -> User:
    subject = str(info.get("sub") or "")
    email = auth.normalise_email(str(info.get("email") or ""))
    name = str(info.get("name") or "")[:120]

    if not subject or not email:
        raise ValueError("Google returned an incomplete profile.")

    # Matched on the provider's subject first: an address can change hands, a
    # subject id cannot.
    existing = (
        await db.execute(
            select(User).where(
                User.oauth_provider == "google", User.oauth_subject == subject
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.email != email:
            existing.email = email
            await db.commit()
        return existing

    # An existing password account with the same address: link them rather than
    # creating a second account for the same person.
    by_email = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if by_email is not None:
        by_email.oauth_provider = "google"
        by_email.oauth_subject = subject
        if not by_email.display_name:
            by_email.display_name = name
        await db.commit()
        return by_email

    user = User(
        email=email,
        password_hash=None,
        display_name=name,
        oauth_provider="google",
        oauth_subject=subject,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Finish the flow and sign the user in.

    Every failure redirects back to the app with a short reason rather than
    rendering an error page: the user is in a browser mid-journey, and a JSON
    body is not a useful thing to land on.
    """
    if not config.GOOGLE_ENABLED:
        raise _unavailable()

    expected = request.cookies.get(STATE_COOKIE)

    def _fail(reason: str) -> RedirectResponse:
        failure = RedirectResponse(_frontend("/", oauth_error=reason), status_code=307)
        failure.delete_cookie(STATE_COOKIE, path="/")
        return failure

    if error:
        # The user pressed cancel, which is not an error worth shouting about.
        return _fail("cancelled")
    if not code:
        return _fail("no_code")
    # Compared in constant time, and a missing cookie fails closed.
    if not expected or not state or not secrets.compare_digest(expected, state):
        return _fail("bad_state")

    try:
        info = await _exchange(code)
        user = await _find_or_create(db, info)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[oauth] google sign-in failed: {exc}")
        return _fail("exchange_failed")

    token = await auth.create_session(db, user)
    response = RedirectResponse(_frontend("/", signed_in="google"), status_code=307)
    auth.set_session_cookie(response, token)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response
