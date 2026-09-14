"""
One error shape for the whole API.

Every failure reaches the client as `{"detail": {code, message, retryable, ...}}`.
The client branches on `code` and decides whether to offer a retry from
`retryable`, which is why a model timeout and an oversized upload must not
arrive looking the same.
"""

from __future__ import annotations

import traceback

from fastapi import HTTPException

import llm


def llm_error(exc: llm.LLMError, stage: str) -> HTTPException:
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


def bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": code, "message": message, "retryable": False},
    )


def conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": code, "message": message, "retryable": False},
    )


def not_found(message: str = "Not found.") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "not_found", "message": message, "retryable": False},
    )


def unexpected(exc: Exception, stage: str) -> HTTPException:
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
