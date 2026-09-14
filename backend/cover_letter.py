"""
Cover letter generation.

The same no-fabrication rule as resume tailoring applies, but it cannot be
enforced the same way. A tailored resume is a list of discrete edits, so an
unsafe one is simply dropped. A cover letter is one continuous piece of prose -
discarding it because a single sentence overreached would leave the candidate
with nothing.

So the letter is returned with its unsupported claims located sentence by
sentence, and the UI makes them impossible to miss before anything is sent.
The letter is editable, which is the right remedy: the candidate knows whether
they have done the thing the sentence claims, and can fix it in seconds.
"""

from __future__ import annotations

import json
import re
from typing import Any

import config
import fabrication
from llm import generate_json

TONES = {
    "professional": "formal, precise, and businesslike",
    "friendly": "warm and conversational while still professional",
    "bold": "confident and direct, leading with impact",
}
DEFAULT_TONE = "professional"

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def _build_prompt(
    profile: dict[str, Any],
    job: dict[str, Any],
    analysis: dict[str, Any],
    tone: str,
) -> str:
    style = TONES.get(tone, TONES[DEFAULT_TONE])
    matched = ", ".join(analysis.get("matched_skills") or []) or "(none identified)"
    skills = ", ".join(profile.get("skills") or []) or "(none listed)"

    return f"""
    You are writing one cover letter for one candidate applying to one job.

    ABSOLUTE RULES - breaking any of these makes the letter harmful:
    1. NEVER claim experience, employers, technologies, qualifications, or metrics
       that are not in the candidate profile below. The candidate has to defend
       every sentence in an interview.
    2. NEVER claim a skill from the job description that the candidate does not have.
    3. Do not invent numbers. If the profile does not contain a figure, do not use one.
    4. Do not invent enthusiasm for specifics you were not told about.

    Write 3 short paragraphs in a {style} tone:
    - Why this role, anchored in something real from the profile.
    - The strongest evidence the candidate can offer for it, drawn only from
      their actual projects or experience.
    - A brief, plain closing.

    Keep it under 250 words. No addresses, no date, no letterhead - just the body.
    Do not use placeholders like [Company] or [Your Name]; use the real values
    given below, and omit anything you were not given.

    Return ONLY valid JSON:
    {{"letter": "<the letter body, paragraphs separated by \\n\\n>"}}

    THE CANDIDATE'S SKILLS (the only skills that may appear):
    {skills}

    Skills this posting wants that the candidate HAS: {matched}

    ROLE: {job.get("title") or "the role"}
    COMPANY: {job.get("company") or "the company"}

    JOB DESCRIPTION:
    {job.get("description") or ""}

    CANDIDATE PROFILE:
    {json.dumps(profile, indent=2)}
    """


def locate_unsupported(
    letter: str, profile: dict[str, Any], job: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """
    Find sentences making claims the profile does not support.

    Reported per sentence rather than as a bare list of words, because "the
    word Kubernetes is unsupported" is far less actionable than being shown the
    sentence to rewrite.

    The employer's name and the role title join the corpus. Naming the company
    you are writing to is not a claim about yourself, and without this every
    letter flags its own opening line - a warning that fires every time is a
    warning nobody reads, which would bury the ones that matter.

    The job *description* stays out. "I have Kubernetes experience" must still
    be caught, and it would not be if wanting Kubernetes counted as evidence of
    having it.
    """
    corpus = fabrication.build_corpus(profile)
    if job:
        corpus |= fabrication.build_corpus(
            {"company": job.get("company") or "", "title": job.get("title") or ""}
        )
    flagged: list[dict[str, Any]] = []

    for match in _SENTENCE.finditer(letter or ""):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        claims = fabrication.find_fabrications(sentence, corpus)
        if claims:
            flagged.append(
                {"sentence": sentence, "claims": claims, "start": match.start()}
            )

    return flagged


async def generate(
    profile: dict[str, Any],
    job: dict[str, Any],
    analysis: dict[str, Any],
    tone: str = DEFAULT_TONE,
) -> dict[str, Any]:
    """Generate a cover letter and locate anything in it the profile cannot back."""
    if tone not in TONES:
        tone = DEFAULT_TONE

    raw = await generate_json(
        _build_prompt(profile, job, analysis, tone),
        timeout=config.ATS_TIMEOUT,
        stage="cover-letter",
        options={"temperature": 0, "top_p": 0, "top_k": 1, "seed": 42},
    )

    letter = raw.get("letter")
    if not isinstance(letter, str):
        letter = ""
    letter = letter.strip()

    unsupported = locate_unsupported(letter, profile, job)
    if unsupported:
        print(
            f"[cover-letter] {len(unsupported)} sentence(s) make unsupported claims: "
            + "; ".join(", ".join(item["claims"]) for item in unsupported)
        )

    return {
        "letter": letter,
        "tone": tone,
        "unsupported": unsupported,
        "word_count": len(letter.split()),
    }
