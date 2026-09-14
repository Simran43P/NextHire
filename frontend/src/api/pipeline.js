// The four pipeline stages, plus the task polling that makes the slow ones
// survivable.
//
// A signed-in user runs the long stages as background tasks: the request
// returns a task id immediately and the result is polled. That is what lets
// someone refresh the page, switch tabs, or close the laptop mid-extraction
// without losing a minute of model time.
//
// A guest runs the same stages synchronously. They have no session to reattach
// with, and their work is not persisted anyway.

import { ApiError, getJson, patchJson, postFile, postJson } from "./client";

export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 5);
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

export const MAX_TITLE_SELECTIONS = 5;
export const MAX_JOB_SELECTIONS = 5;

const POLL_INTERVAL_MS = 1500;

/**
 * Validate a file before it leaves the browser.
 *
 * The server enforces all of this too - a client check is a convenience, never
 * a control - but failing here saves the user an upload that cannot succeed.
 */
export function validateResumeFile(file) {
  if (!file) return "Please choose a PDF file first.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    return `That file is ${mb}MB. The limit is ${MAX_UPLOAD_MB}MB.`;
  }
  const looksLikePdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!looksLikePdf) return "Only PDF resumes are supported.";
  return null;
}

// ---------------------------------------------------------------------------
// Background tasks
// ---------------------------------------------------------------------------

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function getTask(taskId, options = {}) {
  return getJson(`/tasks/${taskId}`, options).then((data) => data.task);
}

export function listActiveTasks(options = {}) {
  return getJson("/tasks", options).then((data) => data.tasks ?? []);
}

/**
 * Poll a task to completion.
 *
 * A failed task carries the same error shape a synchronous call would have
 * thrown, so callers handle one kind of failure rather than two.
 */
export async function awaitTask(taskId, { signal, onTick } = {}) {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

    const task = await getTask(taskId, { signal });
    onTick?.(task);

    if (task.status === "DONE") return task.result ?? {};
    if (task.status === "FAILED") {
      throw new ApiError({
        code: task.error?.code ?? "task_failed",
        message: task.error?.message ?? "That step failed. Please try again.",
        stage: task.error?.stage,
        retryable: task.error?.retryable ?? true,
      });
    }

    await sleep(POLL_INTERVAL_MS);
  }
}

/** Run a stage response to completion, whether it came back done or queued. */
async function settle(response, { signal, onTick } = {}) {
  if (response?.status === "queued" && response.task_id) {
    return { ...(await awaitTask(response.task_id, { signal, onTick })), task_id: response.task_id };
  }
  return response;
}

const backgroundSuffix = (background) => (background ? "?background=true" : "");

// ---------------------------------------------------------------------------
// Stage 1: PDF -> structured profile
// ---------------------------------------------------------------------------

export async function parseResume(file, { onProgress, background = false, signal } = {}) {
  const problem = validateResumeFile(file);
  if (problem) {
    throw new ApiError({ code: "invalid_file", message: problem, retryable: false });
  }

  const response = await postFile(`/parse-resume${backgroundSuffix(background)}`, file, {
    onProgress,
  });
  const data = await settle(response, { signal });

  return {
    profile: data.profile,
    gaps: data.gaps ?? [],
    rawText: data.raw_text ?? "",
    filename: data.filename ?? file.name,
    profileId: data.profile_id ?? null,
    profileVersion: data.profile_version ?? null,
  };
}

// ---------------------------------------------------------------------------
// Profiles (signed in only)
// ---------------------------------------------------------------------------

export function listProfiles(options = {}) {
  return getJson("/profiles", options).then((data) => data.profiles ?? []);
}

export function fetchProfile(profileId, options = {}) {
  return getJson(`/profiles/${profileId}`, options);
}

export function saveProfile(profileId, profile, options = {}) {
  return patchJson(`/profiles/${profileId}`, { profile }, options);
}

// ---------------------------------------------------------------------------
// Stage 2: profile -> ranked job titles
// ---------------------------------------------------------------------------

export async function inferTitles(
  { profile, profileId } = {},
  { background = false, signal } = {}
) {
  const response = await postJson(
    `/infer-titles${backgroundSuffix(background)}`,
    profileId ? { profile_id: profileId } : { profile },
    { signal }
  );
  const data = await settle(response, { signal });
  return data.titles ?? [];
}

// ---------------------------------------------------------------------------
// Stage 3: titles -> live postings
// ---------------------------------------------------------------------------

export async function searchJobs(
  titles,
  { profile, profileId, country, signal } = {}
) {
  const query = country ? `?country=${encodeURIComponent(country)}` : "";
  const data = await postJson(
    `/jobs${query}`,
    {
      job_titles: titles,
      resume_profile: profileId ? null : (profile ?? null),
      profile_id: profileId ?? null,
    },
    { signal }
  );
  return {
    jobs: data.jobs ?? [],
    searchId: data.search_id ?? null,
    warnings: data.warnings ?? [],
    usedMock: Boolean(data.used_mock),
    quotaExhausted: Boolean(data.quota_exhausted),
  };
}

// ---------------------------------------------------------------------------
// Stage 4: profile + posting -> ATS analysis
// ---------------------------------------------------------------------------

/**
 * Analyse one posting.
 *
 * With a profileId and jobId the server caches the result against the profile's
 * current version, so re-opening a job is instant - and correcting the profile
 * invalidates it rather than showing a stale score.
 *
 * Throws on failure. Callers must not substitute a zero score: a failed
 * analysis and a genuine bad match are different outcomes.
 */
export async function analyzeAts(
  { profile, profileId, jobDescription, jobId } = {},
  { background = false, refresh = false, signal } = {}
) {
  const params = new URLSearchParams();
  if (background) params.set("background", "true");
  if (refresh) params.set("refresh", "true");
  const query = params.toString() ? `?${params}` : "";

  const response = await postJson(
    `/analyze-ats${query}`,
    {
      resume_profile: profileId ? null : (profile ?? null),
      job_description: jobId ? null : (jobDescription ?? null),
      profile_id: profileId ?? null,
      job_id: jobId ?? null,
    },
    { signal }
  );
  const data = await settle(response, { signal });
  return data.analysis;
}
