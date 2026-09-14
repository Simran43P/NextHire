"""
ATS match analysis.

Scores a resume profile against one job description and reports what matched,
what is missing, and what to do about it.

Two behaviours here are load-bearing:

**A failure is never a score.** The previous implementation swallowed every
exception and returned `match_score: 0`, which is indistinguishable from a
genuine bad match. A candidate cannot tell "you are a poor fit" from "the model
was not running". Errors now propagate as typed exceptions and the route layer
turns them into real HTTP failures the client renders with a retry.

**Claims are evidenced.** Every matched skill is located in the posting text and
returned with the surrounding sentence, so the candidate can check the
judgement rather than take it on trust.
"""

import json
import re
from typing import Any

import config
import prescore
from llm import generate_json
from schema_utils import clamp_score, clean_str_list

# The shape every analysis is guaranteed to have, whatever the model returned.
ATS_SCHEMA: dict[str, Any] = {
    "match_score": 0,
    "matched_skills": [],
    "missing_skills": [],
    "recommendations": [],
}

# Bands used for the one-line verdict. Ordered high to low; first hit wins.
_VERDICTS: list[tuple[int, str, str]] = [
    (85, "Strong Match", "Your resume covers the core requirements for this role."),
    (70, "Good Match", "Your resume is a good fit, with a few skills worth reinforcing."),
    (55, "Fair Match", "Your resume covers some requirements, but there are real gaps to close."),
    (40, "Weak Match", "Your resume is missing several of the skills this role asks for."),
    (0, "Mismatch", "This role does not align closely with your current resume."),
]

_MAX_EVIDENCE_CHARS = 240

# How far the score may be pulled toward evidenced coverage, in points.
#
# A small model's *score* is the least reliable thing it produces. Its *lists*
# are far better, and unlike the score they are independently checkable: a
# matched skill can be verified against the profile and against the posting
# text. Both observed failures were the score contradicting the model's own
# lists - 85% while crediting skills the posting never mentions, and 10% while
# itself naming four matched skills against seven missing.
#
# So the lists anchor the score, and the model is allowed to modulate it by up
# to this much - importance weighting is real, and a missing core requirement
# should count for more than a missing nice-to-have, which a ratio cannot see.
_MAX_SCORE_ADJUSTMENT = 15


def _build_prompt(
    resume_profile: dict[str, Any], job_description: str, declared_skills: list[str]
) -> str:
    # The flat skill list is repeated outside the JSON blob because a 3B model
    # reliably misses skills buried in a nested profile object - it marked
    # Docker and Git as missing for a candidate whose profile listed both.
    skills_block = ", ".join(declared_skills) if declared_skills else "(none listed)"

    return f"""
    You are an expert Applicant Tracking System (ATS) and Technical Recruiter.
    Your task is to analyze the candidate's profile against the provided job description
    and generate a highly detailed ATS match report.

    Rules:
    1. Be highly critical and objective. If the candidate is missing core requirements, score them lower.
    2. Identify specific technical skills, soft skills, and experiences explicitly mentioned in the Job Description.
    3. Cross-reference those requirements with the Candidate Profile.
    4. Calculate a realistic "match_score" from 0 to 100.
    5. List exactly what matches ("matched_skills") and what is missing ("missing_skills").
    6. Only list a skill under "matched_skills" if it appears in the Candidate Profile. Never credit
       the candidate for a skill their profile does not contain.
    7. Only list a skill under "missing_skills" if the Job Description actually asks for it. Never
       invent a requirement the posting does not state.
    8. CRITICAL: before writing "missing_skills", check every entry against the CANDIDATE'S
       DECLARED SKILLS list below. If a skill appears in that list, the candidate HAS it -
       it belongs in "matched_skills" and must NEVER appear in "missing_skills".
    9. Provide 2-3 specific, actionable recommendations on how the candidate can improve their resume
       for this exact role.

    Return ONLY valid JSON matching this exact schema. Do not include markdown formatting.
    The values below are format placeholders, not example answers.
    {{
      "match_score": "<integer 0-100>",
      "matched_skills": ["<skill from the profile that this posting asks for>"],
      "missing_skills": ["<skill this posting asks for that the profile lacks>"],
      "recommendations": ["<specific, actionable suggestion>"]
    }}

    CANDIDATE'S DECLARED SKILLS (the candidate definitively has all of these):
    {skills_block}

    Job Description:
    {job_description}

    Full Candidate Profile:
    {json.dumps(resume_profile, indent=2)}
    """


def verdict_for(score: int) -> dict[str, str]:
    """Map a score onto its band label and one-line summary."""
    for threshold, label, summary in _VERDICTS:
        if score >= threshold:
            return {"label": label, "summary": summary}
    return {"label": "Mismatch", "summary": _VERDICTS[-1][2]}


def find_evidence(skills: list[str], job_description: str) -> dict[str, str]:
    """
    Locate each skill in the posting and return the sentence around it.

    Done locally with a regex rather than a second model call: it is free,
    instant, and - being a literal search of the source text - it cannot itself
    hallucinate. A skill the model claimed but that does not appear in the
    posting simply gets no evidence, which is useful information in itself.
    """
    if not job_description:
        return {}

    evidence: dict[str, str] = {}
    for skill in skills:
        if not skill.strip():
            continue
        pattern = r"(?<![A-Za-z0-9+#.])({})(?![A-Za-z0-9+#])".format(re.escape(skill))
        match = re.search(pattern, job_description, flags=re.IGNORECASE)
        if not match:
            continue

        # Widen to sentence boundaries around the hit, then trim to a readable
        # length without cutting a word in half.
        start = job_description.rfind(".", 0, match.start())
        start = 0 if start == -1 else start + 1
        end = job_description.find(".", match.end())
        end = len(job_description) if end == -1 else end + 1

        snippet = job_description[start:end].strip()
        if len(snippet) > _MAX_EVIDENCE_CHARS:
            # Keep the match itself centred in what survives the trim.
            local = match.start() - start
            left = max(0, local - _MAX_EVIDENCE_CHARS // 2)
            snippet = snippet[left : left + _MAX_EVIDENCE_CHARS].strip()
            snippet = f"...{snippet}..."

        evidence[skill] = snippet

    return evidence


def reconcile_missing_skills(
    matched: list[str], missing: list[str], declared_skills: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """
    Remove skills the model called missing that the candidate demonstrably has.

    Small models under-read nested profiles: in testing, a profile listing Docker
    and Git among its skills was told both were missing for a posting that asked
    for them. That is not a judgement call the model is entitled to get wrong -
    it is a checkable fact, and checking it here costs nothing.

    Word-boundary matching keeps this conservative: declared "Java" does not
    rescue a missing "JavaScript", and declared "R" does not rescue "React".

    Returns (matched, missing, corrected).
    """
    if not declared_skills:
        return matched, missing, []

    corrected: list[str] = []
    still_missing: list[str] = []

    for skill in missing:
        if prescore.find_skill_matches(declared_skills, skill):
            corrected.append(skill)
            if not any(existing.lower() == skill.lower() for existing in matched):
                matched.append(skill)
        else:
            still_missing.append(skill)

    return matched, still_missing, corrected


def build_analysis(
    raw: Any, job_description: str, resume_profile: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Force raw model output into the guaranteed analysis shape and enrich it.

    Separated from the model call so it can be tested directly against the kinds
    of malformed output a small model actually produces.
    """
    # Coerced field by field from the raw payload rather than template-filled.
    # Template filling discards a wrongly typed value and substitutes the
    # default, which would turn a perfectly usable "88%" into 0 and a bare
    # "Python" into []. These coercers recover the value instead, and still
    # guarantee the type.
    source = raw if isinstance(raw, dict) else {}

    score = clamp_score(source.get("match_score", ATS_SCHEMA["match_score"]))
    matched = clean_str_list(source.get("matched_skills"), limit=30)
    missing = clean_str_list(source.get("missing_skills"), limit=30)
    recommendations = clean_str_list(source.get("recommendations"), limit=5)

    # Correct demonstrable factual errors first, so the score derived from the
    # lists below is built on corrected facts. A skill the model called missing
    # that the candidate's own profile lists is simply wrong.
    declared = prescore.collect_profile_skills(resume_profile or {})
    matched, missing, corrected = reconcile_missing_skills(matched, missing, declared)

    evidence = find_evidence(matched, job_description)

    # Anchor the score to what the lists actually support, then let the model
    # move it by at most _MAX_SCORE_ADJUSTMENT.
    #
    # Only skills evidenced in the posting count toward the numerator: a
    # "matched" skill appearing nowhere in the posting is not a requirement this
    # job stated, so it cannot be evidence of fit. That is what let a Java role
    # score 85% on the strength of Postman, Express and React.
    #
    # Pulling upward is equally necessary. The model reported 10% while its own
    # lists named four matched skills against seven missing - a score its own
    # enumeration contradicts, shown right beside those lists.
    evidenced = len(evidence)
    if evidenced or missing:
        coverage = clamp_score(round(100 * evidenced / (evidenced + len(missing))))

        # Three clauses, each traceable to an observed failure:
        #   - the score may not exceed coverage (the 85% Java role),
        #   - nor sit far below it (the 10% that contradicted its own lists),
        #   - and pessimism within the allowance is left alone, because a
        #     missing core requirement should weigh more than a nice-to-have
        #     and a ratio cannot see the difference.
        anchored = min(coverage, max(score, coverage - _MAX_SCORE_ADJUSTMENT))

        # Whatever the lists imply, the model's own judgement is never moved
        # more than _MAX_SCORE_ADJUSTMENT points.
        score = clamp_score(
            min(score + _MAX_SCORE_ADJUSTMENT, max(score - _MAX_SCORE_ADJUSTMENT, anchored))
        )

    # Lead with the skills the posting actually asks for. The model still
    # over-claims matches; ordering puts the defensible ones first, and the
    # rest carry no quote for the user to open.
    matched.sort(key=lambda skill: skill not in evidence)

    verdict = verdict_for(score)

    return {
        "match_score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "recommendations": recommendations,
        "evidence": evidence,
        "label": verdict["label"],
        "summary": verdict["summary"],
        # Named so the UI can say what was corrected rather than quietly
        # presenting a doctored number.
        "corrected_skills": corrected,
    }


async def analyze_job_match(
    resume_profile: dict[str, Any], job_description: str
) -> dict[str, Any]:
    """
    Analyse one profile against one job description.

    Raises:
        LLMError subclasses. Callers must not convert these into a zero score -
        a failed analysis and a bad match are different outcomes.
    """
    declared = prescore.collect_profile_skills(resume_profile)

    raw = await generate_json(
        _build_prompt(resume_profile, job_description, declared),
        timeout=config.ATS_TIMEOUT,
        stage="ats",
        # Deterministic, like extraction. At temperature 0.1 the same resume and
        # posting scored 73% on one run and 80% on the next, having named 17
        # matched skills the first time and 8 the second. A scoring tool whose
        # answer changes when you press retry cannot be trusted or cached, and
        # the greedy-decoding repetition that a non-zero temperature guards
        # against is not a risk for output this short and this structured.
        options={"temperature": 0, "top_p": 0, "top_k": 1, "seed": 42},
    )

    analysis = build_analysis(raw, job_description, resume_profile)
    print(
        f"[ats] score={analysis['match_score']} ({analysis['label']}) "
        f"matched={len(analysis['matched_skills'])} "
        f"missing={len(analysis['missing_skills'])}"
    )
    if analysis["corrected_skills"]:
        print(
            "[ats] corrected false negatives: "
            + ", ".join(analysis["corrected_skills"])
        )
    return analysis
