"""
The fabrication guard.

These are the most important tests in the project. A resume tool that invents
employment history is not a flawed product, it is a harmful one: the person who
sends that resume is the one who gets caught, and they will not have read the
generated text as carefully as they read their own.

Every case below is a thing a small model actually does when asked to "tailor a
resume for this posting".
"""

import pytest

from fabrication import build_corpus, find_fabrications, screen_changes


@pytest.fixture
def corpus(sample_profile):
    # Python, React, SQL, FastAPI, Git, C++; one project using scikit-learn and
    # Streamlit; B.Tech at CUSAT; AWS Cloud Practitioner.
    return build_corpus(sample_profile)


class TestBuildCorpus:
    def test_it_reaches_every_nested_string(self, corpus):
        assert "python" in corpus          # skills
        assert "scikit-learn" in corpus    # nested in projects
        assert "cusat" in corpus           # nested in education
        assert "kochi" in corpus           # a bare top-level string

    def test_numbers_are_collected(self):
        assert "82" in build_corpus({"experience": [{"achievements": ["Raised to 82%"]}]})

    def test_an_empty_profile_yields_an_empty_corpus(self):
        assert build_corpus({}) == set()


class TestFindFabrications:
    def test_rephrasing_with_the_candidates_own_words_passes(self, corpus):
        assert find_fabrications("Built services in Python backed by SQL.", corpus) == []

    def test_an_invented_technology_is_caught(self, corpus):
        # The classic: the posting wants Kubernetes, so the model claims it.
        assert "Kubernetes" in find_fabrications(
            "Deployed services on Kubernetes in production.", corpus
        )

    def test_an_invented_metric_is_caught(self, corpus):
        # The most damaging kind, and the easiest to say by accident.
        assert "40" in find_fabrications(
            "Improved API performance by 40 percent.", corpus
        )

    def test_an_invented_percentage_is_caught(self, corpus):
        assert any("35" in claim for claim in find_fabrications(
            "Reduced load times by 35%.", corpus
        ))

    def test_an_invented_employer_is_caught(self, corpus):
        assert "Infosys" in find_fabrications("Worked at Infosys on payments.", corpus)

    def test_an_invented_acronym_is_caught(self, corpus):
        assert "GCP" in find_fabrications("Managed GCP infrastructure.", corpus)

    def test_a_sentence_initial_capital_is_not_a_claim(self, corpus):
        # "Developed" only looks like a proper noun because it starts a sentence.
        assert find_fabrications("Developed reporting tools using Python.", corpus) == []

    def test_a_real_skill_is_not_flagged_by_its_casing(self, corpus):
        assert find_fabrications("Used FastAPI and React across projects.", corpus) == []

    def test_punctuated_skills_survive(self, corpus):
        assert find_fabrications("Wrote systems code in C++.", corpus) == []

    def test_a_number_already_in_the_profile_is_allowed(self):
        profile = {"experience": [{"achievements": ["Cut runtime by 40%"]}]}
        assert find_fabrications("Cut runtime 40%.", build_corpus(profile)) == []

    def test_empty_text_is_not_a_fabrication(self, corpus):
        assert find_fabrications("", corpus) == []
        assert find_fabrications("   ", corpus) == []

    def test_multiple_inventions_are_all_reported(self, corpus):
        found = find_fabrications(
            "Led Kubernetes and Terraform work at Infosys, cutting cost 30%.", corpus
        )
        assert {"Kubernetes", "Terraform", "Infosys"} <= set(found)


class TestScreenChanges:
    def test_safe_changes_pass_and_unsafe_ones_are_held_back(self, sample_profile):
        changes = [
            {"id": "c0", "after": "Built data tools in Python and SQL."},
            {"id": "c1", "after": "Ran Kubernetes clusters in production."},
            {"id": "c2", "after": "Shipped a React interface for the ranker."},
        ]
        safe, rejected = screen_changes(changes, sample_profile)

        assert [c["id"] for c in safe] == ["c0", "c2"]
        assert [c["id"] for c in rejected] == ["c1"]

    def test_a_rejected_change_names_what_it_invented(self, sample_profile):
        _, rejected = screen_changes(
            [{"id": "c0", "after": "Deployed with Kubernetes."}], sample_profile
        )
        # Reported rather than dropped silently: knowing what was thrown out is
        # more trustworthy than only seeing what survived.
        assert rejected[0]["fabricated"] == ["Kubernetes"]

    def test_only_the_new_text_is_checked(self, sample_profile):
        # The original may well mention things the tailored version drops; only
        # what the rewrite asserts can be a new claim.
        safe, rejected = screen_changes(
            [{"id": "c0", "before": "Used Kubernetes", "after": "Used Python"}],
            sample_profile,
        )
        assert len(safe) == 1 and rejected == []

    def test_an_empty_change_list_is_fine(self, sample_profile):
        assert screen_changes([], sample_profile) == ([], [])
