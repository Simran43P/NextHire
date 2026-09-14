"""
Structured profile extraction.

Turns raw resume text into a fixed JSON profile using the local model. The
schema is guaranteed on the way out regardless of what the model produced, so
every downstream stage can rely on the shape.
"""

from typing import Any

import config
from llm import generate_json
from schema_utils import validate_against

SCHEMA_TEMPLATE: dict[str, Any] = {
    "name": "",
    "email": "",
    "phone": "",
    "location": "",
    "skills": [],
    "years_of_experience": 0,
    "education": [
        {
            "degree": "",
            "college": "",
            "year": "",
        }
    ],
    "experience": [
        {
            "company": "",
            "designation": "",
            "duration": "",
            "responsibilities": [],
            "achievements": [],
        }
    ],
    "projects": [
        {
            "name": "",
            "description": "",
            "technologies": [],
            "github": "",
            "live_demo": "",
        }
    ],
    "certifications": [],
    "languages": [],
    "links": {
        "github": "",
        "linkedin": "",
        "portfolio": "",
    },
}


def _build_prompt(resume_text: str) -> str:
    """
    Build the extraction prompt.

    Deliberately strict and repetitive: local models like Qwen 2.5 are much less
    steerable than frontier hosted models, so explicit, unambiguous, repeated
    constraints materially reduce hallucination and formatting drift.
    """
    import json

    schema_json = json.dumps(SCHEMA_TEMPLATE, indent=2)

    return f"""You are an expert HR data-extraction assistant.
Your ONLY task is to extract information that is EXPLICITLY present in the resume text below,
and return it as JSON matching the exact schema shown.

STRICT RULES (follow all of them):
1. Do NOT invent, guess, infer, or hallucinate any information that is not explicitly stated in the resume.
2. If a field is not present in the resume, you MUST use the following defaults:
   - Missing string -> ""
   - Missing list -> []
   - Missing integer -> 0
3. Do NOT summarize, rephrase, or embellish. Copy relevant details as they appear in the source text.
4. Return ONLY valid JSON. No markdown, no ```json fences, no explanations, no comments, no trailing text.
5. The JSON keys and nesting MUST exactly match the schema below. Do not add, rename, or remove keys.
6. "years_of_experience" must be a whole number (integer). If it cannot be determined explicitly, use 0.
7. If the resume contains multiple education entries, work experiences, or projects, include all of them
   as separate objects in the corresponding array, each following the same object shape shown below.

Schema (structure only, values below are placeholders/defaults):
{schema_json}

Resume Text:
\"\"\"
{resume_text}
\"\"\"

Return ONLY the JSON object now.
"""


def validate_profile(raw_profile: Any) -> dict[str, Any]:
    """Force any model output into an exact SCHEMA_TEMPLATE-shaped profile."""
    return validate_against(raw_profile, SCHEMA_TEMPLATE)


def profile_is_thin(profile: dict[str, Any]) -> list[str]:
    """
    Report which major sections came back empty.

    Extraction is good, not perfect, and every later stage inherits its errors.
    Naming the gaps lets the review screen point the candidate straight at what
    needs fixing instead of asking them to proof-read the whole thing.
    """
    gaps: list[str] = []
    if not profile.get("name"):
        gaps.append("name")
    if not profile.get("email"):
        gaps.append("email")
    if not profile.get("skills"):
        gaps.append("skills")
    if not any(e.get("company") for e in profile.get("experience") or []):
        if not any(p.get("name") for p in profile.get("projects") or []):
            # Only a problem when there is neither experience nor projects -
            # a fresher with projects and no jobs is normal, not a thin profile.
            gaps.append("experience or projects")
    if not any(e.get("degree") or e.get("college") for e in profile.get("education") or []):
        gaps.append("education")
    return gaps


async def extract_resume_data(resume_text: str) -> dict[str, Any]:
    """
    Extract a structured profile from raw resume text.

    Generation is deterministic - the same resume always produces the same
    profile - so a candidate who re-uploads does not get a different result.

    Raises:
        LLMError subclasses, which the route layer maps to HTTP status codes.
    """
    prompt = _build_prompt(resume_text)

    print(
        f"[extract] resume={len(resume_text)} chars, "
        f"prompt={len(prompt)} chars (~{len(prompt) // 4} tokens)"
    )

    raw_profile = await generate_json(
        prompt,
        timeout=config.EXTRACTION_TIMEOUT,
        stage="extraction",
        options={
            # Deterministic: same input -> same output, every time.
            "temperature": 0,
            "top_p": 0,
            "top_k": 1,
            "repeat_penalty": 1.0,
            "seed": 42,
            # Large context so long, multi-page resumes are not truncated.
            "num_ctx": config.EXTRACTION_NUM_CTX,
        },
    )

    profile = validate_profile(raw_profile)
    gaps = profile_is_thin(profile)
    if gaps:
        print(f"[extract] thin profile, empty sections: {', '.join(gaps)}")

    return {"profile": profile, "gaps": gaps}
