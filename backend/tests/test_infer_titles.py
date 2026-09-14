"""Stage 2 contract: profile -> ranked, deduplicated, board-realistic job titles."""

import pytest

import llm
from infer_titles import (
    MAX_TITLES,
    _deduplicate_job_titles,
    _validate_job_titles,
    infer_job_titles,
    to_api_shape,
)


class TestValidateJobTitles:
    def test_well_formed_entries_survive(self):
        result = _validate_job_titles(
            {"job_titles": [{"title": "Backend Engineer", "confidence": 88, "reason": "Python"}]}
        )
        assert result == [
            {"title": "Backend Engineer", "confidence": 88, "reason": "Python"}
        ]

    def test_missing_key_yields_empty_list_not_an_exception(self):
        assert _validate_job_titles({}) == []
        assert _validate_job_titles({"job_titles": "Backend Engineer"}) == []

    def test_entries_without_a_usable_title_are_dropped(self):
        result = _validate_job_titles(
            {"job_titles": [{"title": ""}, {"title": "   "}, {"confidence": 90}, "junk"]}
        )
        assert result == []

    def test_confidence_is_coerced_and_clamped(self):
        result = _validate_job_titles(
            {
                "job_titles": [
                    {"title": "A", "confidence": "92%"},
                    {"title": "B", "confidence": 150},
                    {"title": "C", "confidence": "high"},
                    {"title": "D"},
                ]
            }
        )
        assert [entry["confidence"] for entry in result] == [92, 100, 0, 0]

    def test_non_string_reason_becomes_empty(self):
        result = _validate_job_titles({"job_titles": [{"title": "A", "reason": 5}]})
        assert result[0]["reason"] == ""


class TestDeduplicate:
    def test_case_insensitive_duplicates_collapse_keeping_highest_confidence(self):
        result = _deduplicate_job_titles(
            [
                {"title": "Data Analyst", "confidence": 70},
                {"title": "data analyst", "confidence": 85},
            ]
        )
        assert len(result) == 1
        assert result[0]["confidence"] == 85

    def test_original_ordering_is_preserved(self):
        result = _deduplicate_job_titles(
            [
                {"title": "A", "confidence": 50},
                {"title": "B", "confidence": 60},
                {"title": "a", "confidence": 99},
            ]
        )
        assert [entry["title"] for entry in result] == ["A", "B"]


class TestApiShape:
    def test_ids_are_stable_and_fields_renamed_for_the_client(self):
        shaped = to_api_shape([{"title": "QA Engineer", "confidence": 64, "reason": "why"}])
        assert shaped == [
            {
                "id": "title-0",
                "title": "QA Engineer",
                "matchPercentage": 64,
                "reason": "why",
            }
        ]


class TestInferJobTitles:
    async def test_results_are_sorted_by_confidence(self, fake_llm, sample_profile):
        fake_llm(
            "infer_titles",
            {
                "job_titles": [
                    {"title": "Data Analyst", "confidence": 60},
                    {"title": "Backend Engineer", "confidence": 91},
                    {"title": "Frontend Developer", "confidence": 75},
                ]
            },
        )
        titles = await infer_job_titles(sample_profile)
        assert [entry["title"] for entry in titles] == [
            "Backend Engineer",
            "Frontend Developer",
            "Data Analyst",
        ]

    async def test_result_is_capped(self, fake_llm, sample_profile):
        fake_llm(
            "infer_titles",
            {"job_titles": [{"title": f"Role {i}", "confidence": i} for i in range(20)]},
        )
        assert len(await infer_job_titles(sample_profile)) == MAX_TITLES

    async def test_malformed_output_degrades_to_an_empty_list(
        self, fake_llm, sample_profile
    ):
        fake_llm("infer_titles", {"unexpected": "shape"})
        assert await infer_job_titles(sample_profile) == []

    async def test_model_failure_propagates(self, fake_llm, sample_profile):
        fake_llm("infer_titles", raises=llm.LLMUnavailableError("down"))
        with pytest.raises(llm.LLMUnavailableError):
            await infer_job_titles(sample_profile)
