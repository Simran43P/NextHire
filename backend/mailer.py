"""
Outbound email, used only for password resets.

Configuring SMTP is optional and deliberately so. With no host set, the reset
link is printed to the server log instead - which is all a single-user local
install needs, costs nothing, and means the reset flow can be developed and
tested without an email provider.

What must never happen is the flow silently failing: if SMTP is configured and
delivery fails, that is logged loudly rather than swallowed.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

import config


def _build_reset_email(to_address: str, reset_url: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Reset your NextHire password"
    message["From"] = config.SMTP_FROM
    message["To"] = to_address
    message.set_content(
        "Someone asked to reset the password for this NextHire account.\n\n"
        f"Open this link to choose a new one:\n{reset_url}\n\n"
        f"The link works once and expires in {config.PASSWORD_RESET_TTL_MINUTES} "
        "minutes.\n\n"
        "If this was not you, you can ignore this email - nothing has changed.\n"
    )
    return message


def _send_blocking(message: EmailMessage) -> None:
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
        server.starttls()
        if config.SMTP_USER and config.SMTP_PASSWORD:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(message)


async def send_password_reset(to_address: str, token: str) -> bool:
    """
    Deliver a reset link. Returns True if it was emailed, False if only logged.

    Never raises: a delivery failure must not turn into a 500 that tells the
    caller whether the address exists.
    """
    reset_url = f"{config.APP_BASE_URL.rstrip('/')}/reset-password?token={token}"

    if not config.SMTP_HOST:
        print(
            "\n[mailer] SMTP is not configured, so the reset link is printed here "
            "instead of emailed:\n"
            f"[mailer]   to:   {to_address}\n"
            f"[mailer]   link: {reset_url}\n"
        )
        return False

    try:
        await asyncio.to_thread(_send_blocking, _build_reset_email(to_address, reset_url))
        print(f"[mailer] password reset sent to {to_address}")
        return True
    except Exception as exc:
        print(f"[mailer] FAILED to send password reset to {to_address}: {exc}")
        print(f"[mailer] link was: {reset_url}")
        return False
