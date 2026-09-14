// The application tracker, cover letters, interview prep, and the skills gap.

import { API_BASE_URL, getJson, patchJson, postJson, request } from "./client";

// ---------------------------------------------------------------------------
// Tracker
// ---------------------------------------------------------------------------

export const STATUSES = ["SAVED", "APPLIED", "INTERVIEWING", "OFFER", "REJECTED"];

export const STATUS_LABELS = {
  SAVED: "Saved",
  APPLIED: "Applied",
  INTERVIEWING: "Interviewing",
  OFFER: "Offer",
  REJECTED: "Rejected",
};

export function fetchBoard(options = {}) {
  return getJson("/applications", options);
}

export function trackJob({ jobId, status = "SAVED", tailoredResumeId = null }) {
  return postJson("/applications", {
    job_id: jobId,
    status,
    tailored_resume_id: tailoredResumeId,
  });
}

export function updateApplication(id, changes) {
  const body = {};
  if (changes.status !== undefined) body.status = changes.status;
  if (changes.notes !== undefined) body.notes = changes.notes;
  if (changes.followUpOn !== undefined) body.follow_up_on = changes.followUpOn;
  if (changes.tailoredResumeId !== undefined) {
    body.tailored_resume_id = changes.tailoredResumeId;
  }
  return patchJson(`/applications/${id}`, body).then((data) => data.application);
}

export function untrackApplication(id) {
  return request(`/applications/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Cover letters
// ---------------------------------------------------------------------------

export const TONES = [
  { value: "professional", label: "Professional" },
  { value: "friendly", label: "Friendly" },
  { value: "bold", label: "Bold" },
];

/**
 * Write a cover letter.
 *
 * `unsupported` holds sentences making claims the profile does not back. Unlike
 * resume edits these are returned rather than discarded - a letter is one piece
 * of prose, and throwing it away over one sentence would leave nothing to work
 * with. The UI has to make them impossible to miss instead.
 */
export async function generateCoverLetter(
  { profile, profileId, job, jobId, analysis, tone } = {},
  { signal } = {}
) {
  const data = await postJson(
    "/cover-letter",
    {
      profile: profileId ? null : (profile ?? null),
      profile_id: profileId ?? null,
      job: jobId ? null : (job ?? null),
      job_id: jobId ?? null,
      analysis: analysis ?? null,
      tone,
    },
    { signal }
  );
  return {
    letter: data.letter ?? "",
    tone: data.tone,
    unsupported: data.unsupported ?? [],
    wordCount: data.word_count ?? 0,
    coverLetterId: data.cover_letter_id ?? null,
  };
}

/** Save an edited letter. The claim check runs again server-side. */
export async function saveCoverLetter(id, content) {
  const data = await patchJson(`/cover-letters/${id}`, { content });
  return { letter: data.letter, unsupported: data.unsupported ?? [] };
}

export async function downloadCoverLetterPdf(content, name = "") {
  const response = await fetch(`${API_BASE_URL}/cover-letter/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, name }),
    credentials: "include",
  });
  if (!response.ok) throw new Error("Could not build the PDF. Please try again.");

  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "cover-letter.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadCoverLetterText(content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "cover-letter.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// ---------------------------------------------------------------------------
// Interview prep and skills gap
// ---------------------------------------------------------------------------

export async function generateInterviewPrep(
  { profile, profileId, job, jobId, analysis } = {},
  { refresh = false, signal } = {}
) {
  const query = refresh ? "?refresh=true" : "";
  const data = await postJson(
    `/interview-prep${query}`,
    {
      profile: profileId ? null : (profile ?? null),
      profile_id: profileId ?? null,
      job: jobId ? null : (job ?? null),
      job_id: jobId ?? null,
      analysis: analysis ?? null,
    },
    { signal }
  );
  return { questions: data.questions, cached: Boolean(data.cached) };
}

export function fetchSkillsGap(options = {}) {
  return getJson("/skills-gap", options);
}
