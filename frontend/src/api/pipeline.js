// The four pipeline stages. This module is the only place that knows the
// backend's route names and payload shapes.

import { ApiError, postFile, postJson } from "./client";

export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 5);
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

/** Cap how many titles and jobs a candidate can carry into the next stage. */
export const MAX_TITLE_SELECTIONS = 5;
export const MAX_JOB_SELECTIONS = 5;

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

/** Stage 1: PDF -> structured profile. */
export async function parseResume(file, { onProgress } = {}) {
  const problem = validateResumeFile(file);
  if (problem) {
    throw new ApiError({ code: "invalid_file", message: problem, retryable: false });
  }

  const data = await postFile("/parse-resume", file, { onProgress });
  return {
    profile: data.profile,
    gaps: data.gaps ?? [],
    rawText: data.raw_text ?? "",
    filename: data.filename ?? file.name,
  };
}

/** Stage 2: profile -> ranked job titles. */
export async function inferTitles(profile, { signal } = {}) {
  const data = await postJson("/infer-titles", profile, { signal });
  return data.titles ?? [];
}

/**
 * Stage 3: titles -> live postings.
 *
 * Passing the profile lets the server annotate every posting with the
 * candidate's own skills that appear in it. That costs nothing - it is a local
 * text comparison, not a model call - and it is what the job cards show
 * instead of the fabricated per-job percentage they used to display.
 */
export async function searchJobs(titles, { profile, country, signal } = {}) {
  const query = country ? `?country=${encodeURIComponent(country)}` : "";
  const data = await postJson(
    `/jobs${query}`,
    { job_titles: titles, resume_profile: profile ?? null },
    { signal }
  );
  return {
    jobs: data.jobs ?? [],
    warnings: data.warnings ?? [],
    usedMock: Boolean(data.used_mock),
    quotaExhausted: Boolean(data.quota_exhausted),
  };
}

/**
 * Stage 4: profile + one job description -> ATS analysis.
 *
 * Throws on failure. Callers must not substitute a zero score - a failed
 * analysis and a genuine bad match are different outcomes and the candidate
 * has to be able to tell them apart.
 */
export async function analyzeAts(profile, jobDescription, { signal } = {}) {
  const data = await postJson(
    "/analyze-ats",
    { resume_profile: profile, job_description: jobDescription },
    { signal }
  );
  return data.analysis;
}
