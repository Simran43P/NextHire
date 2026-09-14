"""
Shape validation for model output.

A local 7B model will occasionally drop a key, return a string where a list
belongs, or invent a nested field. Every model response is forced back into a
known shape here before it can reach a client, so no downstream code - and no
frontend component - ever has to defend against a malformed payload.

`fill_defaults` was previously private to extractor.py. The ATS stage validated
only shallowly, with `.get(key, default)` calls that accepted a string where a
list was required. Both now share this module.
"""

import copy
from typing import Any


def fill_defaults(data: Any, template: Any) -> Any:
    """
    Recursively force `data` into the shape of `template`, substituting the
    template's defaults wherever `data` is missing or the wrong type.

    Three cases:
      - dict: every key in `template` is present in the result, recursing into
        nested dicts and lists.
      - list whose template item is a dict (education, experience, projects):
        every item in `data` is validated against that single item template.
      - scalars: wrong type or missing falls back to the template default.
    """
    if isinstance(template, dict):
        if not isinstance(data, dict):
            data = {}
        return {
            key: fill_defaults(data.get(key), default)
            for key, default in template.items()
        }

    if isinstance(template, list):
        if not isinstance(data, list):
            return []
        if template and isinstance(template[0], dict):
            item_template = template[0]
            return [fill_defaults(item, item_template) for item in data]
        return data

    # bool is a subclass of int, so it must be checked first.
    if isinstance(template, bool):
        return data if isinstance(data, bool) else template
    if isinstance(template, int):
        return data if isinstance(data, int) and not isinstance(data, bool) else template
    if isinstance(template, str):
        return data if isinstance(data, str) else template

    return data if data is not None else template


def validate_against(raw: Any, template: dict[str, Any]) -> dict[str, Any]:
    """Validate `raw` against a template, working on a copy so it is never mutated."""
    return fill_defaults(raw, copy.deepcopy(template))


def clean_str_list(value: Any, *, limit: int | None = None) -> list[str]:
    """
    Coerce a model-supplied value into a clean list of non-empty strings.

    Handles the three things models actually do wrong here: returning a bare
    string instead of a list, mixing numbers into a list of strings, and
    repeating the same entry with different casing.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            item = str(item)
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def clamp_score(value: Any, *, low: int = 0, high: int = 100) -> int:
    """
    Coerce a model-supplied score into an integer inside [low, high].

    Models return scores as floats, as strings, as "85%", and occasionally as
    values outside the range they were told to use.
    """
    if isinstance(value, bool):
        return low
    if isinstance(value, str):
        cleaned = value.strip().rstrip("%").strip()
        try:
            value = float(cleaned)
        except ValueError:
            return low
    if not isinstance(value, (int, float)):
        return low
    return max(low, min(high, int(round(value))))
