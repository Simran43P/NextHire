"""
The fabrication guard.

A resume tool that invents employment history is not a flawed product, it is a
harmful one: the person who sends that resume is the one who gets caught, and
they will not have read the generated text as carefully as they read their own.

So "do not fabricate" cannot be a line in a prompt. It is checked here, after
generation, against the candidate's actual profile - and anything that fails is
discarded before it is ever offered for review.

**What counts as a claim.** Not every word is checkable, but the words that
matter are. A rewrite may reorder, condense, and rephrase freely; it may not
introduce a technology, an organisation, a qualification, or a number that the
source profile does not contain. Those four cover every fabrication that would
actually embarrass someone in an interview.

**Why the job description is not part of the corpus.** Adopting the posting's
vocabulary is exactly how this goes wrong: a posting that asks for Kubernetes
is not evidence the candidate has used it. Only the candidate's own profile
counts as a source of truth about the candidate.
"""

from __future__ import annotations

import re
from typing import Any

# Words that are capitalised in ordinary resume prose without being claims.
# Kept deliberately small: the rule below only examines capitalised words that
# are *not* sentence-initial, so most prose never reaches this list.
_COMMON_CAPITALISED = {
    "i", "a", "an", "the", "and", "or", "but", "for", "with", "to", "of", "in",
    "on", "at", "by", "from", "as", "into", "across", "through", "using", "used",
    "built", "led", "wrote", "designed", "developed", "delivered", "improved",
    "reduced", "increased", "created", "managed", "owned", "shipped", "built",
    "worked", "collaborated", "implemented", "maintained", "supported",
    "responsible", "experience", "team", "teams", "project", "projects",
    "company", "role", "work", "client", "clients", "user", "users", "product",
    "service", "services", "system", "systems", "application", "applications",
    "software", "engineer", "engineering", "developer", "development", "data",
    "web", "mobile", "backend", "frontend", "fullstack", "full", "stack",
    "senior", "junior", "intern", "internship", "manager", "lead",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "present", "current",
}

# A token is worth checking when it carries a specific, verifiable claim.
_ACRONYM = re.compile(r"^[A-Z][A-Z0-9]{1,}$")
_HAS_SYMBOL_OR_DIGIT = re.compile(r"[0-9+#./]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-/]*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:\n])\s+")


def _strings_in(value: Any) -> list[str]:
    """Every string anywhere in a nested structure."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings_in(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings_in(item)]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    return []


def build_corpus(profile: dict[str, Any]) -> set[str]:
    """
    Every token the candidate's own profile actually contains.

    This is the whole definition of truth for the guard, so it is deliberately
    generous about what it collects and strict about nothing else counting.
    """
    corpus: set[str] = set()
    for text in _strings_in(profile):
        lowered = text.lower()
        for token in _WORD.findall(lowered):
            corpus.add(token.strip(".-/"))
        for number in _NUMBER.findall(lowered):
            corpus.add(number)
            corpus.add(number.rstrip("%"))
    return {token for token in corpus if token}


def _is_claim(token: str, *, sentence_initial: bool) -> bool:
    """Whether a token asserts something checkable about the candidate."""
    if _NUMBER.fullmatch(token):
        return True
    if _ACRONYM.match(token):
        return True
    if _HAS_SYMBOL_OR_DIGIT.search(token) and len(token) > 1:
        return True
    if token[:1].isupper() and not sentence_initial:
        return True
    return False


def find_fabrications(text: str, corpus: set[str]) -> list[str]:
    """
    Return the claims in `text` that the profile does not support.

    An empty list means every checkable claim traces back to something the
    candidate actually wrote.
    """
    if not text or not text.strip():
        return []

    unsupported: list[str] = []
    seen: set[str] = set()

    for sentence in _SENTENCE_SPLIT.split(text):
        tokens = _WORD.findall(sentence) + _NUMBER.findall(sentence)
        first_word = _WORD.search(sentence)
        first = first_word.group(0) if first_word else None

        for token in tokens:
            cleaned = token.strip(".-/")
            if not cleaned or len(cleaned) < 2:
                continue

            lowered = cleaned.lower()
            if lowered in _COMMON_CAPITALISED or lowered in seen:
                continue
            if not _is_claim(cleaned, sentence_initial=cleaned == first):
                continue
            if lowered in corpus or lowered.rstrip("%") in corpus:
                continue

            seen.add(lowered)
            unsupported.append(cleaned)

    return unsupported


def check_change(change: dict[str, Any], corpus: set[str]) -> list[str]:
    """Check one proposed rewrite. Only the new text can introduce a claim."""
    return find_fabrications(str(change.get("after") or ""), corpus)


def screen_changes(
    changes: list[dict[str, Any]], profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Split proposed changes into those safe to offer and those to discard.

    Discarded changes are returned rather than dropped silently: telling the
    candidate that four suggestions were thrown out for inventing things is
    more trustworthy than quietly showing them the six that survived.
    """
    corpus = build_corpus(profile)
    safe: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for change in changes:
        fabricated = check_change(change, corpus)
        if fabricated:
            rejected.append({**change, "fabricated": fabricated})
        else:
            safe.append(change)

    return safe, rejected
