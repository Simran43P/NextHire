"""
Stage 4 contract: profile + job description -> a trustworthy analysis.

The behaviour these tests exist to protect: a failed analysis must never be
presentable as a score of zero, because a candidate cannot distinguish "you are
a poor fit" from "the model was not running".
"""

import pytest

import llm
from ats_matcher import (
    analyze_job_match,
    build_analysis,
    find_evidence,
    reconcile_missing_skills,
    verdict_for,
)


class TestBuildAnalysis:
    def test_complete_output_passes_through(self, sample_job_description):
        # Four evidenced matches against one gap puts the evidence ceiling at
        # 80, above the model's own 78, so the score is left alone.
        analysis = build_analysis(
            {
                "match_score": 78,
                "matched_skills": ["Python", "SQL", "FastAPI", "Git"],
                "missing_skills": ["Kubernetes"],
                "recommendations": ["Add cloud experience"],
            },
            sample_job_description,
        )
        assert analysis["match_score"] == 78
        assert analysis["matched_skills"] == ["Python", "SQL", "FastAPI", "Git"]
        assert analysis["missing_skills"] == ["Kubernetes"]
        assert analysis["label"] == "Good Match"

    def test_empty_output_yields_a_complete_zero_analysis(self):
        analysis = build_analysis({}, "")
        assert analysis["match_score"] == 0
        assert analysis["matched_skills"] == []
        assert analysis["recommendations"] == []
        assert analysis["label"] == "Mismatch"

    def test_score_returned_as_a_percent_string_is_parsed(self, sample_job_description):
        assert build_analysis({"match_score": "88%"}, sample_job_description)["match_score"] == 88

    def test_score_outside_range_is_clamped(self, sample_job_description):
        assert build_analysis({"match_score": 140}, sample_job_description)["match_score"] == 100

    def test_skills_returned_as_a_bare_string_are_accepted(self, sample_job_description):
        analysis = build_analysis(
            {"matched_skills": "Python", "missing_skills": "Docker"}, sample_job_description
        )
        assert analysis["matched_skills"] == ["Python"]
        assert analysis["missing_skills"] == ["Docker"]

    def test_duplicate_skills_collapse(self, sample_job_description):
        analysis = build_analysis(
            {"matched_skills": ["Python", "python", "PYTHON"]}, sample_job_description
        )
        assert analysis["matched_skills"] == ["Python"]

    def test_junk_inside_skill_lists_is_dropped(self, sample_job_description):
        analysis = build_analysis(
            {"matched_skills": ["Python", None, {"a": 1}, ""]}, sample_job_description
        )
        assert analysis["matched_skills"] == ["Python"]

    def test_recommendations_are_capped(self, sample_job_description):
        analysis = build_analysis(
            {"recommendations": [f"tip {i}" for i in range(20)]}, sample_job_description
        )
        assert len(analysis["recommendations"]) == 5

    def test_the_shape_is_identical_regardless_of_input_quality(self, sample_job_description):
        expected = {
            "match_score",
            "matched_skills",
            "missing_skills",
            "recommendations",
            "evidence",
            "label",
            "summary",
            "corrected_skills",
        }
        assert set(build_analysis({}, "")) == expected
        assert set(build_analysis("total garbage", sample_job_description)) == expected


class TestReconcileMissingSkills:
    """
    The model marking a skill missing that the candidate's own profile lists is
    a checkable factual error, not a judgement call. Found against the real
    model: a profile listing Docker and Git was told both were missing.
    """

    def test_a_declared_skill_is_moved_out_of_missing(self):
        matched, missing, corrected = reconcile_missing_skills(
            ["Java"], ["Docker", "Spring Boot"], ["Java", "Docker", "Git"]
        )
        assert corrected == ["Docker"]
        assert "Docker" in matched
        assert missing == ["Spring Boot"]

    def test_genuinely_absent_skills_stay_missing(self):
        _, missing, corrected = reconcile_missing_skills(
            [], ["Kubernetes", "Hibernate"], ["Python", "SQL"]
        )
        assert missing == ["Kubernetes", "Hibernate"]
        assert corrected == []

    def test_word_boundaries_prevent_false_rescues(self):
        # Declaring Java must not rescue JavaScript, and R must not rescue React.
        _, missing, corrected = reconcile_missing_skills(
            [], ["JavaScript", "React"], ["Java", "R"]
        )
        assert missing == ["JavaScript", "React"]
        assert corrected == []

    def test_a_corrected_skill_is_not_duplicated_into_matched(self):
        matched, _, _ = reconcile_missing_skills(
            ["docker"], ["Docker"], ["Docker"]
        )
        assert len(matched) == 1

    def test_no_declared_skills_means_no_corrections(self):
        matched, missing, corrected = reconcile_missing_skills(["A"], ["B"], [])
        assert (matched, missing, corrected) == (["A"], ["B"], [])


class TestScoreAnchoring:
    """
    The score is anchored to the skill lists, which - unlike the score itself -
    are independently checkable. Both observed failures were the model's score
    contradicting its own lists.
    """

    POSTING = (
        "We need a Java Developer. Strong Java and SQL required. "
        "Spring Boot and Hibernate experience essential. Docker is a plus."
    )

    def analyse(self, score, matched, missing, posting=None, profile=None):
        return build_analysis(
            {
                "match_score": score,
                "matched_skills": matched,
                "missing_skills": missing,
                "recommendations": [],
            },
            self.POSTING if posting is None else posting,
            profile,
        )

    def test_an_over_confident_score_is_pulled_down(self):
        # Only Java and SQL appear in the posting; React, Postman and Express
        # are skills the posting never asks for and cannot be evidence of fit.
        analysis = self.analyse(
            90, ["Java", "SQL", "React", "Postman", "Express"], ["Spring Boot", "Hibernate"]
        )
        # Coverage is 2/(2+2) = 50, reached from 90 but capped at 15 points.
        assert analysis["match_score"] == 75

    def test_a_score_contradicting_its_own_lists_is_pulled_up(self):
        # The real failure: the model reported 10% while naming four matched
        # skills against seven missing.
        analysis = self.analyse(
            10,
            ["Java", "SQL", "Docker", "Spring"],
            ["Hibernate", "Kafka", "Redis", "AWS", "GraphQL", "Terraform", "gRPC"],
        )
        # Coverage is 4/(4+7) = 36; the score is lifted to within 15 of it.
        assert analysis["match_score"] == 21

    def test_a_verbose_missing_list_cannot_collapse_the_score(self):
        # Nine missing against one evidenced gives 10% coverage; the model's 45%
        # may only be pulled down 15 points.
        analysis = self.analyse(
            45,
            ["Java"],
            ["Spring Boot", "Hibernate", "Kafka", "Redis", "AWS",
             "GraphQL", "Terraform", "Kubernetes", "Elasticsearch"],
        )
        assert analysis["match_score"] == 30

    def test_mild_pessimism_within_the_allowance_is_left_alone(self):
        # Coverage is 3/(3+1) = 75 and the model said 70. A ratio cannot see
        # that a missing core requirement outweighs a missing nice-to-have, so
        # the model keeps its say while it stays close to the lists.
        analysis = self.analyse(70, ["Java", "SQL", "Docker"], ["Hibernate"])
        assert analysis["match_score"] == 70

    def test_the_adjustment_is_bounded_in_both_directions(self):
        for score in (0, 20, 50, 80, 100):
            for matched, missing in (
                (["Java"], ["A", "B", "C", "D", "E"]),
                (["Java", "SQL", "Docker"], []),
            ):
                result = self.analyse(score, matched, missing)["match_score"]
                assert abs(result - score) <= 15

    def test_no_anchoring_without_lists_to_anchor_to(self):
        analysis = self.analyse(80, [], [], posting="")
        assert analysis["match_score"] == 80


class TestFactualCorrection:
    """
    A skill the model calls missing that the candidate's profile lists is not a
    judgement call - it is wrong, and correcting it changes what the score is
    derived from.
    """

    def analyse(self, score, matched, missing, profile, posting=""):
        return build_analysis(
            {
                "match_score": score,
                "matched_skills": matched,
                "missing_skills": missing,
                "recommendations": [],
            },
            posting,
            profile,
        )

    def test_a_falsely_missing_skill_is_moved_and_reported(self, sample_profile):
        # sample_profile lists Python, React, SQL, FastAPI, Git, C++.
        analysis = self.analyse(
            40, ["Python", "SQL"], ["Git", "FastAPI", "Kubernetes"], sample_profile
        )
        assert analysis["corrected_skills"] == ["Git", "FastAPI"]
        assert analysis["missing_skills"] == ["Kubernetes"]
        assert "Git" in analysis["matched_skills"]

    def test_correcting_the_lists_raises_the_score(self, sample_profile):
        posting = "Requires Python, SQL, Git and FastAPI. Kubernetes a plus."
        uncorrected = self.analyse(
            40, ["Python", "SQL"], ["Git", "FastAPI", "Kubernetes"], None, posting
        )
        corrected = self.analyse(
            40, ["Python", "SQL"], ["Git", "FastAPI", "Kubernetes"], sample_profile, posting
        )
        assert corrected["match_score"] > uncorrected["match_score"]

    def test_genuinely_absent_skills_are_not_rescued(self, sample_profile):
        analysis = self.analyse(
            50, ["Python"], ["Kubernetes", "Terraform"], sample_profile
        )
        assert analysis["corrected_skills"] == []
        assert analysis["missing_skills"] == ["Kubernetes", "Terraform"]

    def test_without_a_profile_nothing_is_corrected(self):
        analysis = self.analyse(40, ["Python"], ["Docker"], None)
        assert analysis["corrected_skills"] == []


class TestVerdictFor:
    @pytest.mark.parametrize(
        "score,label",
        [
            (100, "Strong Match"),
            (85, "Strong Match"),
            (84, "Good Match"),
            (70, "Good Match"),
            (69, "Fair Match"),
            (55, "Fair Match"),
            (54, "Weak Match"),
            (40, "Weak Match"),
            (39, "Mismatch"),
            (0, "Mismatch"),
        ],
    )
    def test_bands(self, score, label):
        assert verdict_for(score)["label"] == label

    def test_every_band_carries_a_summary_sentence(self):
        for score in (95, 75, 60, 45, 10):
            assert verdict_for(score)["summary"].strip()


class TestFindEvidence:
    def test_a_matched_skill_is_quoted_from_the_posting(self, sample_job_description):
        evidence = find_evidence(["FastAPI"], sample_job_description)
        assert "FastAPI" in evidence["FastAPI"]

    def test_a_skill_absent_from_the_posting_gets_no_evidence(self, sample_job_description):
        # The model claiming a skill the posting never mentions is exactly the
        # case worth surfacing, so it is simply left unevidenced.
        assert find_evidence(["Haskell"], sample_job_description) == {}

    def test_long_snippets_are_trimmed_and_marked(self):
        description = "Intro. " + ("filler words " * 60) + "Kubernetes " + ("more " * 60) + "."
        evidence = find_evidence(["Kubernetes"], description)
        snippet = evidence["Kubernetes"]
        assert len(snippet) <= 260
        assert "Kubernetes" in snippet
        assert snippet.startswith("...") and snippet.endswith("...")

    def test_no_description_yields_no_evidence(self):
        assert find_evidence(["Python"], "") == {}


class TestAnalyzeJobMatch:
    async def test_returns_an_enriched_analysis(
        self, fake_llm, sample_profile, sample_job_description
    ):
        fake_llm(
            "ats_matcher",
            {
                "match_score": 72,
                "matched_skills": ["Python", "FastAPI", "SQL", "Git"],
                "missing_skills": ["Kubernetes"],
                "recommendations": ["Mention container experience"],
            },
        )
        analysis = await analyze_job_match(sample_profile, sample_job_description)

        assert analysis["match_score"] == 72
        assert analysis["label"] == "Good Match"
        assert "FastAPI" in analysis["evidence"]

    async def test_both_the_profile_and_the_posting_reach_the_prompt(
        self, fake_llm, sample_profile
    ):
        calls = fake_llm("ats_matcher", {"match_score": 50})
        await analyze_job_match(sample_profile, "UNIQUE-POSTING-MARKER")
        assert "UNIQUE-POSTING-MARKER" in calls[0]
        assert "Asha Menon" in calls[0]

    @pytest.mark.parametrize(
        "error",
        [
            llm.LLMTimeoutError("slow"),
            llm.LLMUnavailableError("down"),
            llm.LLMInvalidJSONError("garbage"),
        ],
    )
    async def test_failures_raise_and_are_never_reported_as_a_zero_score(
        self, fake_llm, sample_profile, sample_job_description, error
    ):
        fake_llm("ats_matcher", raises=error)
        with pytest.raises(llm.LLMError):
            await analyze_job_match(sample_profile, sample_job_description)
