"""
Free, local, per-posting keyword overlap.

The job cards previously showed a match percentage that was the *title-level*
confidence copied onto every posting returned for that title. Several unrelated
jobs displayed an identical number that read as a per-job score and was not one.

The honest fix without spending a model call on every posting is to report what
can actually be computed for free: how many of the candidate's own skills appear
verbatim in the posting text, and which ones. That is a genuine per-posting
signal, it is instant and deterministic, and - crucially - it is reported as a
count of named skills rather than as a percentage, so it cannot be mistaken for
the real ATS score that arrives later.
"""

import re
from typing import Any

# Skills whose names are punctuation-heavy or substring-prone need exact,
# case-insensitive matching rather than a naive `in` test. "R" must not match
# every capital R in the posting, and "C++" must survive regex escaping.
_WORD_BOUNDARY = r"(?<![A-Za-z0-9+#.])({})(?![A-Za-z0-9+#])"


def collect_profile_skills(profile: dict[str, Any]) -> list[str]:
    """
    Gather every skill-like term from a profile: the declared skills list plus
    the technologies named in projects, which is where a fresher's real skills
    usually live.
    """
    terms: list[str] = []

    for skill in profile.get("skills") or []:
        if isinstance(skill, str) and skill.strip():
            terms.append(skill.strip())

    for project in profile.get("projects") or []:
        if not isinstance(project, dict):
            continue
        for tech in project.get("technologies") or []:
            if isinstance(tech, str) and tech.strip():
                terms.append(tech.strip())

    # Deduplicate case-insensitively, keeping first-seen casing.
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def find_skill_matches(skills: list[str], text: str) -> list[str]:
    """Return the subset of `skills` that appear in `text`, preserving order."""
    if not text:
        return []

    matched: list[str] = []
    for skill in skills:
        if not skill:
            continue
        pattern = _WORD_BOUNDARY.format(re.escape(skill))
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched.append(skill)
    return matched


def score_job(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """
    Annotate a single posting with its keyword overlap against the profile.

    Returns the fields to merge into the job, never a percentage:
      keyword_matches   - how many distinct profile skills appear in the posting
      matched_keywords  - which ones, so the UI can show them rather than a number
    """
    skills = collect_profile_skills(profile)
    haystack = " ".join(
        str(job.get(field) or "")
        for field in ("title", "description", "company")
    )
    matched = find_skill_matches(skills, haystack)
    return {
        "keyword_matches": len(matched),
        "matched_keywords": matched,
    }


def annotate_jobs(
    profile: dict[str, Any] | None, jobs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Add keyword overlap to every posting, in place, and sort the strongest
    overlap first so the most promising postings are the ones a candidate sees
    when choosing which five to spend a real analysis on.

    With no profile supplied the postings are returned untouched and the UI
    simply shows no pre-score.
    """
    if not profile:
        return jobs

    for job in jobs:
        job.update(score_job(profile, job))

    jobs.sort(key=lambda j: j.get("keyword_matches", 0), reverse=True)
    return jobs
