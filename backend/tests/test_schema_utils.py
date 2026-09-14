"""Shape validation is what stops malformed model output reaching a client."""

from schema_utils import clamp_score, clean_str_list, fill_defaults, validate_against

TEMPLATE = {
    "name": "",
    "count": 0,
    "tags": [],
    "items": [{"label": "", "value": 0}],
    "nested": {"a": "", "b": 0},
}


class TestFillDefaults:
    def test_missing_keys_get_defaults(self):
        assert fill_defaults({}, TEMPLATE) == {
            "name": "",
            "count": 0,
            "tags": [],
            "items": [],
            "nested": {"a": "", "b": 0},
        }

    def test_wrong_scalar_types_fall_back(self):
        result = fill_defaults({"name": 42, "count": "seven"}, TEMPLATE)
        assert result["name"] == ""
        assert result["count"] == 0

    def test_booleans_are_not_accepted_as_integers(self):
        # bool subclasses int in Python; an unguarded isinstance check lets
        # True through as a count of 1.
        assert fill_defaults({"count": True}, TEMPLATE)["count"] == 0

    def test_repeating_objects_are_validated_individually(self):
        result = fill_defaults(
            {"items": [{"label": "ok"}, {"value": 3}, "not an object"]}, TEMPLATE
        )
        assert result["items"] == [
            {"label": "ok", "value": 0},
            {"label": "", "value": 3},
            {"label": "", "value": 0},
        ]

    def test_unexpected_keys_are_dropped(self):
        result = fill_defaults({"name": "x", "surprise": "!"}, TEMPLATE)
        assert "surprise" not in result

    def test_non_dict_input_yields_a_full_default_object(self):
        assert fill_defaults("garbage", TEMPLATE)["nested"] == {"a": "", "b": 0}

    def test_template_is_not_mutated(self):
        before = dict(TEMPLATE)
        validate_against({"tags": ["a"]}, TEMPLATE)
        assert TEMPLATE == before


class TestCleanStrList:
    def test_bare_string_becomes_a_single_item_list(self):
        assert clean_str_list("Python") == ["Python"]

    def test_numbers_are_coerced_and_junk_dropped(self):
        assert clean_str_list(["Python", 3, None, {"a": 1}, "  "]) == ["Python", "3"]

    def test_case_insensitive_deduplication_keeps_first_casing(self):
        assert clean_str_list(["React", "react", "REACT"]) == ["React"]

    def test_limit_is_respected(self):
        assert clean_str_list(["a", "b", "c"], limit=2) == ["a", "b"]

    def test_non_list_non_string_yields_empty(self):
        assert clean_str_list(None) == []
        assert clean_str_list(7) == []


class TestClampScore:
    def test_plain_integer_passes_through(self):
        assert clamp_score(73) == 73

    def test_out_of_range_is_clamped(self):
        assert clamp_score(150) == 100
        assert clamp_score(-20) == 0

    def test_float_is_rounded(self):
        assert clamp_score(72.6) == 73

    def test_percent_string_is_parsed(self):
        assert clamp_score("85%") == 85
        assert clamp_score(" 42 ") == 42

    def test_unparseable_values_become_zero(self):
        assert clamp_score("high") == 0
        assert clamp_score(None) == 0
        assert clamp_score(True) == 0
