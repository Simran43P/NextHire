"""
The free per-posting keyword signal.

This replaced the title-level confidence that used to be stamped onto every
posting returned for a title, which made unrelated jobs display an identical
number that read as a per-job match score.
"""

from prescore import annotate_jobs, collect_profile_skills, find_skill_matches, score_job


class TestCollectProfileSkills:
    def test_declared_skills_and_project_technologies_are_merged(self, sample_profile):
        skills = collect_profile_skills(sample_profile)
        assert "Python" in skills          # declared
        assert "scikit-learn" in skills    # from a project

    def test_duplicates_collapse_case_insensitively(self):
        skills = collect_profile_skills(
            {"skills": ["React", "react"], "projects": [{"technologies": ["REACT"]}]}
        )
        assert skills == ["React"]

    def test_missing_sections_are_tolerated(self):
        assert collect_profile_skills({}) == []
        assert collect_profile_skills({"skills": None, "projects": None}) == []

    def test_non_string_entries_are_ignored(self):
        assert collect_profile_skills({"skills": ["Go", 7, None, "  "]}) == ["Go"]


class TestFindSkillMatches:
    def test_matching_is_case_insensitive(self):
        assert find_skill_matches(["python"], "We use Python daily.") == ["python"]

    def test_substrings_of_longer_words_do_not_count(self):
        # "R" must not match the R in "React", and "Java" must not match
        # "JavaScript" - the classic keyword-matching false positives.
        assert find_skill_matches(["R"], "Strong React experience") == []
        assert find_skill_matches(["Java"], "Expert in JavaScript") == []

    def test_punctuation_heavy_skills_survive(self):
        assert find_skill_matches(["C++"], "Systems work in C++ and Rust") == ["C++"]
        assert find_skill_matches([".NET"], "Built on .NET Core") == [".NET"]

    def test_order_is_preserved(self):
        matched = find_skill_matches(["SQL", "Python"], "Python and SQL required")
        assert matched == ["SQL", "Python"]

    def test_empty_text_matches_nothing(self):
        assert find_skill_matches(["Python"], "") == []


class TestScoreJob:
    def test_reports_a_count_and_the_named_skills_never_a_percentage(
        self, sample_profile, sample_job_description
    ):
        result = score_job(sample_profile, {"description": sample_job_description})
        assert set(result) == {"keyword_matches", "matched_keywords"}
        assert result["keyword_matches"] == len(result["matched_keywords"])
        assert "Python" in result["matched_keywords"]
        assert "FastAPI" in result["matched_keywords"]
        # Not asked for by this posting, so not matched.
        assert "React" not in result["matched_keywords"]

    def test_title_and_company_are_searched_too(self, sample_profile):
        result = score_job(sample_profile, {"title": "Python Developer", "description": ""})
        assert "Python" in result["matched_keywords"]


class TestAnnotateJobs:
    def test_strongest_overlap_is_sorted_first(self, sample_profile):
        jobs = [
            {"id": "a", "description": "We use Java and Spring."},
            {"id": "b", "description": "Python, SQL, FastAPI and Git required."},
        ]
        annotated = annotate_jobs(sample_profile, jobs)
        assert annotated[0]["id"] == "b"
        assert annotated[0]["keyword_matches"] > annotated[1]["keyword_matches"]

    def test_without_a_profile_jobs_pass_through_unannotated(self):
        jobs = [{"id": "a", "description": "Python"}]
        assert annotate_jobs(None, jobs) == [{"id": "a", "description": "Python"}]
