"""Stage 1 contract: raw resume text -> a profile matching SCHEMA_TEMPLATE exactly."""

import pytest

import llm
from extractor import (
    SCHEMA_TEMPLATE,
    extract_resume_data,
    profile_is_thin,
    validate_profile,
)


class TestValidateProfile:
    def test_empty_model_output_still_yields_the_full_schema(self):
        profile = validate_profile({})
        assert set(profile) == set(SCHEMA_TEMPLATE)
        assert profile["name"] == ""
        assert profile["skills"] == []
        assert profile["years_of_experience"] == 0
        assert profile["links"] == {"github": "", "linkedin": "", "portfolio": ""}

    def test_dropped_nested_keys_are_restored(self):
        profile = validate_profile({"links": {"github": "https://gh/x"}})
        assert profile["links"]["github"] == "https://gh/x"
        assert profile["links"]["linkedin"] == ""

    def test_experience_entries_are_individually_shaped(self):
        profile = validate_profile(
            {"experience": [{"company": "Acme"}, {"designation": "Intern"}]}
        )
        assert profile["experience"][0]["responsibilities"] == []
        assert profile["experience"][1]["company"] == ""

    def test_years_of_experience_must_be_an_integer(self):
        assert validate_profile({"years_of_experience": "three"})["years_of_experience"] == 0
        assert validate_profile({"years_of_experience": 3})["years_of_experience"] == 3

    def test_invented_top_level_keys_are_discarded(self):
        profile = validate_profile({"salary_expectation": "20 LPA"})
        assert "salary_expectation" not in profile


class TestProfileIsThin:
    def test_complete_profile_reports_no_gaps(self, sample_profile):
        assert profile_is_thin(sample_profile) == []

    def test_missing_core_fields_are_named(self):
        gaps = profile_is_thin(validate_profile({}))
        assert "name" in gaps and "email" in gaps and "skills" in gaps

    def test_fresher_with_projects_is_not_flagged_for_missing_experience(
        self, sample_profile
    ):
        assert sample_profile["experience"] == []
        assert "experience or projects" not in profile_is_thin(sample_profile)

    def test_no_experience_and_no_projects_is_flagged(self, sample_profile):
        sample_profile["projects"] = []
        assert "experience or projects" in profile_is_thin(sample_profile)


class TestExtractResumeData:
    async def test_returns_validated_profile_and_gaps(self, fake_llm):
        fake_llm("extractor", {"name": "Asha Menon", "skills": ["Python"]})
        result = await extract_resume_data("some resume text")

        assert result["profile"]["name"] == "Asha Menon"
        assert result["profile"]["skills"] == ["Python"]
        # Schema completed even though the model returned only two keys.
        assert result["profile"]["certifications"] == []
        assert "email" in result["gaps"]

    async def test_resume_text_reaches_the_prompt(self, fake_llm):
        calls = fake_llm("extractor", {})
        await extract_resume_data("UNIQUE-RESUME-MARKER")
        assert "UNIQUE-RESUME-MARKER" in calls[0]

    async def test_model_failure_propagates_rather_than_returning_a_blank_profile(
        self, fake_llm
    ):
        fake_llm("extractor", raises=llm.LLMTimeoutError("too slow"))
        with pytest.raises(llm.LLMTimeoutError):
            await extract_resume_data("some resume text")
