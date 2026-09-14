"""
Job title inference.

Takes a structured profile and infers the job titles the candidate should
actually apply for, ranked by confidence. Weighted towards skills and projects
so that freshers are not penalised for having no employment history.
"""

import json
from typing import Any

import config
from llm import generate_json

MAX_TITLES = 5


def _build_prompt(resume_profile: dict[str, Any]) -> str:
    return f"""
    You are an expert technical recruiter specializing in entry-level and early-career hiring.
    Analyze the candidate profile below and infer the TOP {MAX_TITLES} most suitable and realistic job titles
    they should apply for.

    Prioritize signals in this order:
    1. Technical skills
    2. Technologies used in projects
    3. Internship experience (if available)
    4. Previous work experience (if available)
    5. Education
    6. Certifications

    Rules:
    - If the candidate is a fresher with little or no work experience, infer entry-level job
      titles based primarily on their projects and skills. Do NOT penalize the candidate for
      lacking experience.
    - Only recommend job titles that are commonly found on real job boards
      (e.g. LinkedIn, Greenhouse, Lever, Indeed, RemoteOK, Arbeitnow).
    - Do NOT invent creative, non-standard, or made-up job titles.
    - Do NOT recommend senior or managerial positions unless clearly justified by the
      candidate's experience.
    - Remove duplicate or nearly identical job titles.
    - Rank the job titles from best match to least match.
    - Assign a confidence score from 0 to 100 for every job title, reflecting how well the
      candidate's profile matches that title.
    - For every job title, give a "reason" of at most 15 words naming the specific skills or
      projects that led you to it.

    Return ONLY valid JSON matching this exact schema. Do not include markdown formatting,
    explanations, or any text outside the JSON object.

    The values below are FORMAT PLACEHOLDERS describing what each field must contain.
    They are NOT example answers. Never copy them into your response.
    {{
        "job_titles": [
            {{
                "title": "<a real job board title>",
                "confidence": "<integer 0-100>",
                "reason": "<max 15 words naming skills or projects FROM THE PROFILE BELOW>"
            }}
        ]
    }}

    Every "reason" must cite only skills, technologies, or projects that appear in the
    candidate profile below. Do not mention any technology the profile does not contain.

    Candidate Profile:
    {json.dumps(resume_profile, indent=2)}
    """


def _validate_job_titles(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Keep only well-formed entries. Returns an empty list rather than raising, so
    a malformed model response degrades to "no titles found" instead of a 500.
    """
    job_titles = structured_data.get("job_titles")
    if not isinstance(job_titles, list):
        return []

    valid: list[dict[str, Any]] = []
    for entry in job_titles:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            continue

        confidence = entry.get("confidence", 0)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence.strip().rstrip("%"))
            except ValueError:
                confidence = 0
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = 0
        confidence = max(0, min(100, int(round(confidence))))

        reason = entry.get("reason")
        if not isinstance(reason, str):
            reason = ""

        valid.append(
            {
                "title": title.strip(),
                "confidence": confidence,
                "reason": reason.strip(),
            }
        )
    return valid


def _deduplicate_job_titles(job_titles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse case-insensitive duplicates, keeping the highest confidence of the
    set but the casing and position of the entry that appeared first - so
    "Data Analyst" is never replaced by a later "data analyst".
    """
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for entry in job_titles:
        key = entry["title"].strip().lower()
        if key not in seen:
            seen[key] = dict(entry)
            order.append(key)
            continue

        existing = seen[key]
        if entry.get("confidence", 0) > existing.get("confidence", 0):
            existing["confidence"] = entry["confidence"]
            if entry.get("reason"):
                existing["reason"] = entry["reason"]

    return [seen[key] for key in order]


def to_api_shape(job_titles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal entries into the shape the client consumes."""
    return [
        {
            "id": f"title-{index}",
            "title": entry["title"],
            "matchPercentage": entry.get("confidence", 0),
            "reason": entry.get("reason", ""),
        }
        for index, entry in enumerate(job_titles)
    ]


async def infer_job_titles(resume_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Infer the top job titles for a profile, ranked best first.

    Raises:
        LLMError subclasses, which the route layer maps to HTTP status codes.
    """
    structured = await generate_json(
        _build_prompt(resume_profile),
        timeout=config.INFERENCE_TIMEOUT,
        stage="inference",
        options={"temperature": 0.2},
    )

    titles = _deduplicate_job_titles(_validate_job_titles(structured))
    titles.sort(key=lambda entry: entry.get("confidence", 0), reverse=True)
    titles = titles[:MAX_TITLES]

    print(f"[infer] {len(titles)} title(s): " + ", ".join(
        f"{t['title']} ({t['confidence']}%)" for t in titles
    ))

    return titles
