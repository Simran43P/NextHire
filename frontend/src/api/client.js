// Shared HTTP layer. Every backend call goes through here so that failures
// arrive at components in one predictable shape.
//
// The backend distinguishes a model timeout from an unreachable model from a
// bad request, and says whether retrying is worth it. Components need that
// distinction - an ATS analysis that failed must never be rendered as a score
// of zero - so none of it is flattened into a generic "something went wrong".

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor({ code, message, status, stage, retryable }) {
    super(message);
    this.name = "ApiError";
    this.code = code ?? "unknown_error";
    this.status = status ?? 0;
    this.stage = stage ?? null;
    this.retryable = retryable ?? true;
  }
}

const NETWORK_ERROR = {
  code: "network_error",
  message:
    "Could not reach the NextHire server. Check that the backend is running on " +
    "port 8000, then try again.",
  retryable: true,
};

/**
 * Turn a non-OK response into an ApiError, preserving the backend's own code
 * and message where it supplied them.
 */
async function toApiError(response) {
  let detail = null;
  try {
    const body = await response.json();
    detail = body?.detail ?? null;
  } catch {
    // A non-JSON error body (a proxy error page, say) - fall through.
  }

  if (detail && typeof detail === "object") {
    return new ApiError({ ...detail, status: response.status });
  }

  return new ApiError({
    code: "http_error",
    message:
      typeof detail === "string" && detail
        ? detail
        : `The server returned an error (${response.status}).`,
    status: response.status,
    retryable: response.status >= 500,
  });
}

/**
 * Send a request and return the parsed body, or throw an ApiError.
 *
 * `credentials: "include"` is not optional. The session lives in an httpOnly
 * cookie, and the API is on a different port from the dev server, so without it
 * every authenticated request arrives anonymous.
 */
export async function request(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(NETWORK_ERROR);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return null;
  return response.json();
}

export function getJson(path, options = {}) {
  return request(path, { ...options, method: "GET" });
}

export function postJson(path, body, options = {}) {
  return request(path, { ...options, method: "POST", body: body ?? {} });
}

export function patchJson(path, body, options = {}) {
  return request(path, { ...options, method: "PATCH", body: body ?? {} });
}

/** GET a binary response as a Blob - used for the stored resume PDF. */
export async function getBlob(path) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }
  if (!response.ok) throw await toApiError(response);
  return response.blob();
}

/**
 * Upload a file with real progress reporting.
 *
 * Uses XMLHttpRequest rather than fetch because fetch cannot report upload
 * progress, and a resume upload followed by a minute of model inference needs
 * to show the user which of the two it is currently doing.
 */
export function postFile(path, file, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);

    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}${path}`);
    // Same reason as credentials: "include" above - the session cookie has to
    // travel with the upload or it arrives as a guest.
    request.withCredentials = true;

    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });

    request.addEventListener("load", () => {
      let body = null;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        // Non-JSON response body - handled by the fallbacks below.
      }

      if (request.status >= 200 && request.status < 300) {
        resolve(body);
        return;
      }

      const detail = body?.detail;
      if (detail && typeof detail === "object") {
        reject(new ApiError({ ...detail, status: request.status }));
      } else {
        reject(
          new ApiError({
            code: "http_error",
            message:
              typeof detail === "string" && detail
                ? detail
                : `Upload failed (${request.status}).`,
            status: request.status,
            retryable: request.status >= 500,
          })
        );
      }
    });

    request.addEventListener("error", () => reject(new ApiError(NETWORK_ERROR)));
    request.addEventListener("timeout", () =>
      reject(
        new ApiError({
          code: "timeout",
          message: "The upload timed out. Please try again.",
          retryable: true,
        })
      )
    );

    request.send(form);
  });
}
