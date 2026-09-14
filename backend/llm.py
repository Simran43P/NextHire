"""
Shared async client for the local Ollama model.

Three things live here that used to be duplicated (or missing) across
extractor.py, infer_titles.py, and ats_matcher.py:

1. **Async I/O.** The previous modules used blocking `requests` inside `async
   def` route handlers, which stalls the whole event loop for the duration of
   the call - up to five minutes for extraction. One user's upload froze the
   server for everyone.

2. **Bounded concurrency.** A single Ollama instance serving one model does not
   parallelise well. A semaphore caps how many calls are actually in flight, so
   the client can fire requests in parallel and render each result as it lands
   without thrashing the model.

3. **Typed errors.** A timeout, an unreachable model, and malformed JSON are
   three different failures and the caller must be able to tell them apart. The
   ATS stage in particular must never present a failure as a score of zero.
"""

import asyncio
import json
import time
from typing import Any

import httpx

import config


class LLMError(Exception):
    """Base class for every model-call failure. Carries a stable machine code."""

    code = "llm_error"
    http_status = 502
    message = "The analysis model could not be reached."

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(detail or self.message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    http_status = 504
    message = "The model took too long to respond. Please try again."


class LLMUnavailableError(LLMError):
    code = "llm_unavailable"
    http_status = 503
    message = (
        "Could not reach the local model. Check that Ollama is running "
        f"and the model is installed."
    )


class LLMInvalidJSONError(LLMError):
    code = "llm_invalid_json"
    http_status = 502
    message = "The model returned a malformed response. Please try again."


# A single shared client and semaphore, created lazily because both need a
# running event loop.
_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.LLM_CONCURRENCY)
    return _semaphore


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient()
    return _client


async def close_client() -> None:
    """Release the shared client. Called from the app's shutdown hook."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def generate_json(
    prompt: str,
    *,
    timeout: int,
    stage: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send a prompt to Ollama and return the parsed JSON object it produced.

    Ollama is asked to constrain its output to valid JSON, but that is not a
    guarantee, so the response is parsed defensively and a parse failure is
    raised as its own error type.

    Args:
        prompt: The fully built prompt.
        timeout: Hard ceiling in seconds for this call.
        stage: Short label used in log lines ("extraction", "inference", "ats").
        options: Ollama generation options merged over the defaults.

    Raises:
        LLMTimeoutError, LLMUnavailableError, LLMInvalidJSONError
    """
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": options or {},
    }

    started = time.monotonic()
    async with _get_semaphore():
        queued_for = time.monotonic() - started
        if queued_for > 1:
            print(f"[llm:{stage}] waited {queued_for:.1f}s for a free slot")

        call_started = time.monotonic()
        try:
            response = await _get_client().post(
                config.OLLAMA_URL, json=payload, timeout=timeout
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"{stage} exceeded the {timeout}s ceiling"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailableError(
                f"{stage} got HTTP {exc.response.status_code} from the model"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"{stage} could not reach the model: {exc}") from exc

    elapsed = time.monotonic() - call_started
    print(f"[llm:{stage}] completed in {elapsed:.1f}s")

    try:
        body = response.json()
    except ValueError as exc:
        raise LLMInvalidJSONError(f"{stage}: Ollama response was not JSON") from exc

    raw = body.get("response")
    if not isinstance(raw, str) or not raw.strip():
        raise LLMInvalidJSONError(f"{stage}: model returned an empty response")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMInvalidJSONError(f"{stage}: model output was not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise LLMInvalidJSONError(
            f"{stage}: expected a JSON object, got {type(parsed).__name__}"
        )

    return parsed
