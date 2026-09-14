"""
Interview preparation.

Questions for one posting, split three ways. The split is the useful part: a
flat list of twenty questions is a wall, whereas knowing which three exist
purely because of a gap in your resume tells you where to spend the evening.

Unlike the resume and cover letter stages there is no fabrication risk here -
the output is questions about the job, not claims about the candidate - so the
generated text needs shaping rather than guarding.
"""

from __future__ import annotations

import json
from typing import Any

import config
from llm import generate_json
from schema_utils import clean_str_list

CATEGORIES = ("technical", "behavioural", "gaps")
MAX_PER_CATEGORY = 6


def _build_prompt(
    profile: dict[str, Any], job: dict[str, Any], analysis: dict[str, Any]
) -> str:
    matched = ", ".join(analysis.get("matched_skills") or []) or "(none identified)"
    missing = ", ".join(analysis.get("missing_skills") or []) or "(none identified)"

    return f"""
    You are an interviewer preparing to interview this candidate for this role.
    Write the questions you would actually ask.

    Produce three groups:
    - "technical": questions about the technologies and problems this role involves,
      pitched at the candidate's actual level. Prefer things their own projects and
      experience invite you to probe.
    - "behavioural": questions about how they work, collaborate, and handle setbacks.
    - "gaps": questions that specifically probe what this posting asks for and the
      candidate's resume does not evidence. These are the ones they will be least
      ready for, which is exactly why they matter.

    Rules:
    - Up to {MAX_PER_CATEGORY} questions per group. Fewer is fine.
    - Each question is one sentence. No preamble, no numbering.
    - Do not ask about technologies that appear in neither the posting nor the profile.
    - For every "gaps" question, name the specific missing skill it is probing.

    Return ONLY valid JSON:
    {{
      "technical": ["<question>"],
      "behavioural": ["<question>"],
      "gaps": [{{"question": "<question>", "probes": "<the missing skill>"}}]
    }}

    ROLE: {job.get("title") or "the role"} at {job.get("company") or "the company"}

    Skills the candidate HAS that this role wants: {matched}
    Skills this role wants that the candidate LACKS: {missing}

    JOB DESCRIPTION:
    {job.get("description") or ""}

    CANDIDATE PROFILE:
    {json.dumps(profile, indent=2)}
    """


def shape(raw: Any) -> dict[str, Any]:
    """Force model output into the three-group shape, whatever it returned."""
    source = raw if isinstance(raw, dict) else {}

    technical = clean_str_list(source.get("technical"), limit=MAX_PER_CATEGORY)
    behavioural = clean_str_list(source.get("behavioural"), limit=MAX_PER_CATEGORY)

    gaps: list[dict[str, str]] = []
    seen: set[str] = set()
    raw_gaps = source.get("gaps")
    if isinstance(raw_gaps, str):
        raw_gaps = [raw_gaps]
    for entry in raw_gaps or []:
        if isinstance(entry, str):
            question, probes = entry.strip(), ""
        elif isinstance(entry, dict):
            question = str(entry.get("question") or "").strip()
            probes = str(entry.get("probes") or "").strip()
        else:
            continue
        if not question or question.lower() in seen:
            continue
        seen.add(question.lower())
        gaps.append({"question": question, "probes": probes})
        if len(gaps) >= MAX_PER_CATEGORY:
            break

    return {"technical": technical, "behavioural": behavioural, "gaps": gaps}


async def generate(
    profile: dict[str, Any], job: dict[str, Any], analysis: dict[str, Any]
) -> dict[str, Any]:
    raw = await generate_json(
        _build_prompt(profile, job, analysis),
        timeout=config.ATS_TIMEOUT,
        stage="interview",
        options={"temperature": 0, "top_p": 0, "top_k": 1, "seed": 42},
    )

    questions = shape(raw)
    print(
        f"[interview] {len(questions['technical'])} technical, "
        f"{len(questions['behavioural'])} behavioural, {len(questions['gaps'])} gap"
    )
    return questions
