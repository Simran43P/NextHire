"""
Resume tailoring.

Turns an ATS analysis into a concrete set of proposed edits, each one
reviewable on its own. The candidate accepts or rejects individually and the
accepted set is applied to produce a tailored profile.

**Edits are located by content, not by path.** The model is asked to quote the
exact line it wants to change rather than to describe where it lives. A 3B model
will not reliably produce `experience[0].responsibilities[1]`, but it will
reliably copy a sentence - and a quote that cannot be found in the source is
itself a useful signal that the model invented the line it claims to be editing.

**Nothing reaches the candidate unscreened.** Every proposal goes through the
fabrication guard first; anything introducing a claim the profile does not
support is discarded before review.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import config
import fabrication
from llm import generate_json
from schema_utils import clean_str_list

MAX_REWRITES = 12

# Fields a rewrite is allowed to touch. Everything else - employers, dates,
# degrees, institutions - is factual record and is never rewritten.
_REWRITABLE = (
    ("experience", ("responsibilities", "achievements")),
    ("projects", ("description",)),
)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _build_prompt(
    profile: dict[str, Any], job_description: str, analysis: dict[str, Any]
) -> str:
    matched = ", ".join(analysis.get("matched_skills") or []) or "(none identified)"
    missing = ", ".join(analysis.get("missing_skills") or []) or "(none identified)"
    skills = ", ".join(profile.get("skills") or []) or "(none listed)"

    return f"""
    You are an expert resume writer preparing one candidate's resume for one specific job.

    ABSOLUTE RULES - breaking any of these makes your output useless and harmful:
    1. NEVER invent experience, employers, job titles, dates, degrees, certifications,
       technologies, tools, or metrics. If the candidate's resume does not say it, you
       may not write it.
    2. NEVER add a number, percentage, or measurement that is not already in the resume.
       Do not invent "improved performance by 40%".
    3. You may ONLY reorder, condense, clarify, and rephrase what is already there.
    4. Every "improved" line must be supported entirely by the original line it replaces.
    5. If a line cannot be improved without inventing something, leave it out of your response.

    Your task:
    - Write a 2-sentence professional summary using ONLY facts already in the profile,
      positioned towards this role.
    - Reorder the candidate's EXISTING skills so the ones this posting asks for come
      first. Do not add or remove any skill.
    - Rewrite up to {MAX_REWRITES} bullet points or project descriptions to use the
      posting's phrasing for work the candidate has ALREADY described.

    For each rewrite, copy the "original" text EXACTLY as it appears in the profile
    below, character for character. If you cannot copy it exactly, skip that rewrite.

    Return ONLY valid JSON in this shape. The values are format placeholders, not
    example answers:
    {{
      "summary": "<2 sentences, facts from the profile only>",
      "skills_order": ["<every existing skill, reordered>"],
      "rewrites": [
        {{
          "original": "<exact text copied from the profile>",
          "improved": "<same claim, phrased for this posting>",
          "why": "<max 12 words>"
        }}
      ]
    }}

    THE CANDIDATE'S SKILLS (the only skills that may appear anywhere):
    {skills}

    Skills this posting asks for that the candidate HAS: {matched}
    Skills this posting asks for that the candidate LACKS: {missing}
    Never claim any of the skills the candidate lacks.

    JOB DESCRIPTION:
    {job_description}

    CANDIDATE PROFILE:
    {json.dumps(profile, indent=2)}
    """


def _collect_rewritable(profile: dict[str, Any]) -> dict[str, str]:
    """Map every rewritable line's normalised text to its path."""
    located: dict[str, str] = {}

    for section, fields in _REWRITABLE:
        for index, entry in enumerate(profile.get(section) or []):
            if not isinstance(entry, dict):
                continue
            for field in fields:
                value = entry.get(field)
                if isinstance(value, str):
                    if value.strip():
                        located.setdefault(_normalise(value), f"{section}.{index}.{field}")
                elif isinstance(value, list):
                    for position, item in enumerate(value):
                        if isinstance(item, str) and item.strip():
                            located.setdefault(
                                _normalise(item), f"{section}.{index}.{field}.{position}"
                            )
    return located


def validate_changes(
    raw: dict[str, Any], profile: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Turn raw model output into located, well-formed change proposals.

    A rewrite whose "original" cannot be found in the profile is dropped: the
    model either paraphrased what it claimed to be quoting, or invented the line
    outright, and neither is something to apply.
    """
    changes: list[dict[str, Any]] = []
    located = _collect_rewritable(profile)

    summary = raw.get("summary")
    if isinstance(summary, str) and summary.strip():
        changes.append(
            {
                "kind": "summary",
                "path": "summary",
                "before": "",
                "after": summary.strip(),
                "why": "A summary positioned at this role",
            }
        )

    existing = profile.get("skills") or []
    proposed_order = clean_str_list(raw.get("skills_order"))
    if proposed_order and existing:
        by_lower = {skill.lower(): skill for skill in existing}
        reordered = [by_lower[s.lower()] for s in proposed_order if s.lower() in by_lower]
        # Anything the model dropped is appended rather than lost - this is a
        # reordering, and silently deleting a skill is not reordering.
        reordered += [s for s in existing if s not in reordered]
        if reordered != list(existing):
            changes.append(
                {
                    "kind": "skills",
                    "path": "skills",
                    "before": ", ".join(existing),
                    "after": ", ".join(reordered),
                    "why": "Skills this posting asks for moved to the front",
                    "value": reordered,
                }
            )

    rewrites = raw.get("rewrites")
    if isinstance(rewrites, list):
        seen_paths: set[str] = set()
        for entry in rewrites[: MAX_REWRITES * 2]:
            if not isinstance(entry, dict):
                continue
            original = str(entry.get("original") or "")
            improved = str(entry.get("improved") or "")
            if not original.strip() or not improved.strip():
                continue

            path = located.get(_normalise(original))
            if path is None or path in seen_paths:
                continue
            if _normalise(original) == _normalise(improved):
                continue

            seen_paths.add(path)
            changes.append(
                {
                    "kind": "bullet",
                    "path": path,
                    "before": original.strip(),
                    "after": improved.strip(),
                    "why": str(entry.get("why") or "").strip()[:120],
                }
            )
            if len(seen_paths) >= MAX_REWRITES:
                break

    for index, change in enumerate(changes):
        change["id"] = f"c{index}"

    return changes


def _set_at_path(target: dict[str, Any], path: str, value: Any) -> bool:
    """Write a value at a dotted path. Returns False if the path no longer fits."""
    parts = path.split(".")
    node: Any = target

    for part in parts[:-1]:
        key: Any = int(part) if part.isdigit() else part
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return False

    last = parts[-1]
    key = int(last) if last.isdigit() else last
    try:
        node[key] = value
    except (KeyError, IndexError, TypeError):
        return False
    return True


def apply_changes(
    profile: dict[str, Any], changes: list[dict[str, Any]], accepted_ids: list[str]
) -> dict[str, Any]:
    """Apply the accepted subset, returning a new profile. The source is untouched."""
    accepted = {str(identifier) for identifier in accepted_ids}
    tailored = copy.deepcopy(profile)

    for change in changes:
        if change.get("id") not in accepted:
            continue

        kind = change.get("kind")
        if kind == "summary":
            tailored["summary"] = change["after"]
        elif kind == "skills":
            tailored["skills"] = change.get("value") or [
                part.strip() for part in change["after"].split(",") if part.strip()
            ]
        else:
            _set_at_path(tailored, change["path"], change["after"])

    return tailored


async def propose_optimisations(
    profile: dict[str, Any], job_description: str, analysis: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate reviewable edits for one posting.

    Returns the proposals that survived screening alongside the ones discarded
    for inventing something, because the rejects are worth seeing.
    """
    raw = await generate_json(
        _build_prompt(profile, job_description, analysis),
        timeout=config.ATS_TIMEOUT,
        stage="optimise",
        # Deterministic, like every other stage: the same resume and posting
        # should not produce a different set of suggestions on a retry.
        options={"temperature": 0, "top_p": 0, "top_k": 1, "seed": 42},
    )

    changes = validate_changes(raw, profile)
    safe, rejected = fabrication.screen_changes(changes, profile)

    # Renumber so accepted ids are contiguous over what is actually offered.
    for index, change in enumerate(safe):
        change["id"] = f"c{index}"

    print(
        f"[optimise] {len(safe)} change(s) offered, "
        f"{len(rejected)} discarded for unsupported claims"
    )
    if rejected:
        for change in rejected:
            print(f"[optimise]   rejected ({', '.join(change['fabricated'])})")

    return {"changes": safe, "rejected": rejected}
