"""
Account-level operations: take your data out, or remove it entirely.

Both exist because a resume is unusually personal - full name, phone number,
home location, employment history - and someone who hands that over is owed a
way to get it back and a way to make it go away.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import config
import errors
import persistence
import storage
from db import get_db
from models import User

router = APIRouter(prefix="/api/account", tags=["account"])


class DeleteAccountRequest(BaseModel):
    # Re-authentication, because deletion is irreversible and a logged-in
    # browser someone walked away from should not be enough to trigger it.
    password: str = ""
    # An account created through Google has no password to re-enter, so it
    # confirms by typing its own address instead. Something deliberate is still
    # required; the point is proof of intent, not proof of a password.
    confirm_email: str = ""


@router.get("/export")
async def export_account(
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """Everything stored about this account, as JSON."""
    payload = await persistence.export_everything(db, user.id)
    payload["account"] = {
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    return payload


@router.post("/delete")
async def delete_account(
    request: Request,
    response: Response,
    payload: DeleteAccountRequest,
    user: User = Depends(auth.current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete the account.

    Rows go via the cascade on `users`; the uploaded PDFs are removed from disk
    separately, because the database knows their keys but not their bytes. Files
    are deleted first - an orphaned row is recoverable, an orphaned resume on
    disk is the thing that should not survive.
    """
    if user.password_hash:
        if not auth.verify_password(user.password_hash, payload.password):
            raise errors.bad_request(
                "invalid_credentials", "That password is not right."
            )
    elif auth.normalise_email(payload.confirm_email) != user.email:
        raise errors.bad_request(
            "confirm_email_mismatch",
            "Type your email address exactly to confirm deletion.",
        )

    user_id = user.id
    await storage.delete_user_files(user_id)
    await auth.destroy_all_sessions(db, user_id)

    await db.delete(user)
    await db.commit()

    auth.clear_session_cookie(response)
    print(f"[account] deleted account {user_id} and all of its files")
    return {
        "status": "success",
        "message": "Your account and everything in it has been deleted.",
    }


@router.get("/limits")
async def limits(user: User | None = Depends(auth.optional_user)):
    """What the current caller is allowed to do. Used to set expectations in the UI."""
    return {
        "status": "success",
        "signed_in": user is not None,
        "has_password": bool(user.password_hash) if user else False,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "uploads_per_hour": config.RATE_LIMIT_UPLOAD_PER_HOUR,
        "analyses_per_hour": config.RATE_LIMIT_INFERENCE_PER_HOUR,
        "persistence": user is not None,
    }
