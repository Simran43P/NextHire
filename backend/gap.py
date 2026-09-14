"""
Skills gap across everything a candidate has analysed.

One analysis tells you what a single posting wants. Ten analyses tell you what
the market you are applying into wants, which is a different and more useful
question - and it is the one thing here that needs no model call at all, only
arithmetic over results already stored.

**The lift estimate is real, not decorative.** "Learn Docker and gain 7%" is
trivially easy to make up. Instead each estimate re-runs the actual scoring
rule with that one skill moved from missing to supported, and reports the
difference. It is still an estimate - it assumes the skill would be evidenced
in the posting text and that nothing else changes - and it is labelled as one.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import resources
from ats_matcher import anchor_score

# Below this, a "gap" is one posting's idiosyncratic ask rather than a pattern
# worth spending weeks of study on.
MIN_OCCURRENCES = 1
TOP_N = 5


def _display_name(variants: list[str]) -> str:
    """Pick the most common spelling, preferring the one with capitals."""
    counts: dict[str, int] = defaultdict(int)
    for variant in variants:
        counts[variant] += 1
    return max(counts, key=lambda name: (counts[name], any(c.isupper() for c in name)))


def analyse_gaps(analyses: list[dict[str, Any]], *, top_n: int = TOP_N) -> dict[str, Any]:
    """
    Rank the skills whose absence costs the candidate most.

    Each analysis must carry `match_score`, `missing_skills`, `evidence` and
    enough context to name the posting.
    """
    if not analyses:
        return {"gaps": [], "analysed": 0, "average_score": None}

    total = len(analyses)
    average = round(sum(a["match_score"] for a in analyses) / total)

    # skill key -> {variants, postings, total_lift}
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"variants": [], "postings": [], "total_lift": 0}
    )

    for analysis in analyses:
        missing = [s for s in (analysis.get("missing_skills") or []) if str(s).strip()]
        evidenced = len(analysis.get("evidence") or {})
        current = int(analysis.get("match_score") or 0)

        for skill in missing:
            key = str(skill).strip().lower()
            # What this posting would score with that one skill supported.
            estimated = anchor_score(
                current, evidenced=evidenced + 1, missing_count=max(0, len(missing) - 1)
            )
            bucket = buckets[key]
            bucket["variants"].append(str(skill).strip())
            bucket["postings"].append(
                {
                    "job_id": analysis.get("job_id"),
                    "title": analysis.get("title") or "",
                    "company": analysis.get("company") or "",
                    "current_score": current,
                    "estimated_score": estimated,
                }
            )
            bucket["total_lift"] += max(0, estimated - current)

    gaps = []
    for key, bucket in buckets.items():
        occurrences = len(bucket["postings"])
        if occurrences < MIN_OCCURRENCES:
            continue
        gaps.append(
            {
                "skill": _display_name(bucket["variants"]),
                "occurrences": occurrences,
                "share": round(100 * occurrences / total),
                # Averaged over every analysis, not only the ones it appears in:
                # a skill missing from one posting in ten does not lift the
                # average by as much as one missing from nine.
                "average_lift": round(bucket["total_lift"] / total, 1),
                # Official docs where the skill is one we curate, and a search
                # otherwise. Never a guessed tutorial URL.
                "resources": resources.for_skill(_display_name(bucket["variants"])),
                "postings": bucket["postings"],
            }
        )

    gaps.sort(key=lambda gap: (gap["average_lift"], gap["occurrences"]), reverse=True)

    return {
        "gaps": gaps[:top_n],
        "analysed": total,
        "average_score": average,
        "projected_average": _projected(analyses, gaps[:top_n]),
    }


def _projected(analyses: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> int | None:
    """
    The average score if every listed gap were closed.

    Computed by re-scoring each posting with all of its listed gaps supported,
    rather than by adding the individual lifts together - those overlap, and
    summing them would overstate the result.
    """
    if not analyses or not gaps:
        return None

    wanted = {gap["skill"].lower() for gap in gaps}
    total = 0
    for analysis in analyses:
        missing = [s for s in (analysis.get("missing_skills") or []) if str(s).strip()]
        closed = [s for s in missing if str(s).strip().lower() in wanted]
        evidenced = len(analysis.get("evidence") or {})
        total += anchor_score(
            int(analysis.get("match_score") or 0),
            evidenced=evidenced + len(closed),
            missing_count=len(missing) - len(closed),
        )
    return round(total / len(analyses))
