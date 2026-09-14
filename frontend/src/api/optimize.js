// Resume optimisation: propose edits, apply the accepted ones, download a PDF.

import { API_BASE_URL, getJson, postJson } from "./client";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Ask for tailored edits against one posting.
 *
 * Everything that comes back under `changes` has already passed the server's
 * fabrication guard. `rejected` holds the suggestions it threw out for claiming
 * something the profile does not support - worth showing, because "we discarded
 * four suggestions on your behalf" is the clearest possible evidence that the
 * remaining ones can be trusted.
 */
export async function proposeChanges(
  { profile, profileId, jobDescription, jobId, analysis } = {},
  { signal } = {}
) {
  const data = await postJson(
    "/optimize",
    {
      profile: profileId ? null : (profile ?? null),
      profile_id: profileId ?? null,
      job_description: jobId ? null : (jobDescription ?? null),
      job_id: jobId ?? null,
      analysis: analysis ?? null,
    },
    { signal }
  );
  return { changes: data.changes ?? [], rejected: data.rejected ?? [] };
}

/** Apply the accepted subset and re-score against the same posting. */
export async function applyChanges(
  {
    profile,
    profileId,
    jobDescription,
    jobId,
    changes,
    acceptedIds,
    rejected = [],
    beforeScore = null,
  } = {},
  { signal } = {}
) {
  const data = await postJson(
    "/optimize/apply",
    {
      profile: profileId ? null : (profile ?? null),
      profile_id: profileId ?? null,
      job_description: jobId ? null : (jobDescription ?? null),
      job_id: jobId ?? null,
      changes,
      accepted_ids: acceptedIds,
      rejected_changes: rejected,
      before_score: beforeScore,
    },
    { signal }
  );
  return {
    tailoredProfile: data.tailored_profile,
    afterAnalysis: data.after_analysis,
    beforeScore: data.before_score,
    afterScore: data.after_score,
    tailoredResumeId: data.tailored_resume_id ?? null,
  };
}

/**
 * Download the tailored resume.
 *
 * Fetched as a blob and saved from memory rather than linked to directly: the
 * stored route needs the session cookie, and a plain anchor would not send it.
 */
export async function downloadPdf({ profile, tailoredResumeId }) {
  const response = tailoredResumeId
    ? await fetch(`${API_BASE_URL}/tailored-resumes/${tailoredResumeId}/pdf`, {
        credentials: "include",
      })
    : await fetch(`${API_BASE_URL}/optimize/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
        credentials: "include",
      });

  if (!response.ok) throw new Error("Could not build the PDF. Please try again.");

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFrom(response) ?? "resume-tailored.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked on the next tick; revoking immediately can cancel the download in
  // some browsers before it has started reading the blob.
  await sleep(0);
  URL.revokeObjectURL(url);
}

function filenameFrom(response) {
  const header = response.headers.get("content-disposition") ?? "";
  const match = header.match(/filename="?([^"]+)"?/);
  return match ? match[1] : null;
}

/** Tailored resumes this account has already produced, newest first. */
export function listTailoredResumes(jobId = null, options = {}) {
  const query = jobId ? `?job_id=${jobId}` : "";
  return getJson(`/tailored-resumes${query}`, options).then(
    (data) => data.tailored_resumes ?? []
  );
}
