"""
In-process rate limiting.

Every model call costs real compute on the machine running Ollama, and the
upload and inference endpoints are trivially abusable by anyone who can reach
them. A fixed-window counter per identity is crude but sufficient here, and
needs no Redis, no extra service, and no cost.

The limitation worth knowing: counters live in this process, so they reset on
restart and would not be shared between two instances. That is a problem for
the day there are two instances, not for a single local install.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

import config

# bucket -> identity -> (window start, count)
_counters: dict[str, dict[str, tuple[float, int]]] = defaultdict(dict)

_WINDOW_SECONDS = 3600


def _identity(request: Request, user_id: int | None) -> str:
    """
    Prefer the account, fall back to the peer address.

    An account is the meaningful unit - one person behind one IP should not be
    throttled by a housemate, and one person across many IPs should not escape
    the limit by changing networks.
    """
    if user_id is not None:
        return f"user:{user_id}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def check(request: Request, bucket: str, limit: int, user_id: int | None = None) -> None:
    """Consume one unit from a bucket, raising 429 when the window is exhausted."""
    if not config.RATE_LIMIT_ENABLED or limit <= 0:
        return

    identity = _identity(request, user_id)
    now = time.monotonic()
    window_start, count = _counters[bucket].get(identity, (now, 0))

    if now - window_start >= _WINDOW_SECONDS:
        window_start, count = now, 0

    if count >= limit:
        retry_after = int(_WINDOW_SECONDS - (now - window_start))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": (
                    "You have made a lot of requests in a short time. "
                    f"Please try again in {max(1, retry_after // 60)} minute(s)."
                ),
                "retryable": True,
            },
            headers={"Retry-After": str(max(1, retry_after))},
        )

    _counters[bucket][identity] = (window_start, count + 1)


def reset() -> None:
    """Clear every counter. Used by tests."""
    _counters.clear()
