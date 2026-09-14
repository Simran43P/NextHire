"""
Turning model output into reviewable edits, and applying the accepted subset.

The load-bearing behaviour: a rewrite whose "original" cannot be found in the
profile is discarded. The model either paraphrased what it claimed to be
quoting or invented the line outright, and neither is something to apply to
somebody's resume.
"""

import pytest

import llm
from optimizer import apply_changes, propose_optimisations, validate_changes


@pytest.fixture
def profile():
    return {
        "name": "Asha Menon",
        "skills": ["Python", "SQL", "React", "Git"],
        "experience": [
            {
                "company": "Zeta Labs",
                "designation": "Intern",
                "duration": "2024",
                "responsibilities": ["Built internal reporting tools in Python"],
                "achievements": ["Cut report runtime by 40%"],
            }
        ],
        "projects": [
            {
                "name": "Resume Ranker",
                "description": "Ranked resumes against postings",
                "technologies": ["Python"],
            }
        ],
    }


class TestValidateChanges:
    def test_a_summary_becomes_a_change(self, profile):
        changes = validate_changes({"summary": "Backend engineer with Python."}, profile)
        assert changes[0]["kind"] == "summary"
        assert changes[0]["id"] == "c0"

    def test_a_reorder_becomes_a_change_that_keeps_every_skill(self, profile):
        changes = validate_changes({"skills_order": ["SQL", "Python"]}, profile)
        reorder = next(c for c in changes if c["kind"] == "skills")
        # React and Git were omitted by the model; a reorder must not delete them.
        assert set(reorder["value"]) == set(profile["skills"])
        assert reorder["value"][:2] == ["SQL", "Python"]

    def test_an_unchanged_order_produces_no_change(self, profile):
        changes = validate_changes({"skills_order": profile["skills"]}, profile)
        assert not any(c["kind"] == "skills" for c in changes)

    def test_a_rewrite_is_located_by_its_quoted_text(self, profile):
        changes = validate_changes(
            {
                "rewrites": [
                    {
                        "original": "Built internal reporting tools in Python",
                        "improved": "Built Python reporting services",
                        "why": "matches posting language",
                    }
                ]
            },
            profile,
        )
        rewrite = next(c for c in changes if c["kind"] == "bullet")
        assert rewrite["path"] == "experience.0.responsibilities.0"

    def test_whitespace_differences_still_locate(self, profile):
        changes = validate_changes(
            {
                "rewrites": [
                    {
                        "original": "  Built   internal reporting tools in Python ",
                        "improved": "Built Python reporting services",
                    }
                ]
            },
            profile,
        )
        assert any(c["kind"] == "bullet" for c in changes)

    def test_a_quote_that_is_not_in_the_profile_is_discarded(self, profile):
        # The model paraphrased instead of quoting, or invented the line.
        changes = validate_changes(
            {
                "rewrites": [
                    {
                        "original": "Led a team of twelve engineers",
                        "improved": "Led a large engineering team",
                    }
                ]
            },
            profile,
        )
        assert not any(c["kind"] == "bullet" for c in changes)

    def test_a_rewrite_that_changes_nothing_is_discarded(self, profile):
        changes = validate_changes(
            {
                "rewrites": [
                    {
                        "original": "Built internal reporting tools in Python",
                        "improved": "Built internal reporting tools in Python",
                    }
                ]
            },
            profile,
        )
        assert not any(c["kind"] == "bullet" for c in changes)

    def test_the_same_line_is_only_rewritten_once(self, profile):
        changes = validate_changes(
            {
                "rewrites": [
                    {"original": "Built internal reporting tools in Python", "improved": "A"},
                    {"original": "Built internal reporting tools in Python", "improved": "B"},
                ]
            },
            profile,
        )
        assert len([c for c in changes if c["kind"] == "bullet"]) == 1

    def test_project_descriptions_are_rewritable(self, profile):
        changes = validate_changes(
            {
                "rewrites": [
                    {
                        "original": "Ranked resumes against postings",
                        "improved": "Ranked resumes against live job postings",
                    }
                ]
            },
            profile,
        )
        assert any(c["path"] == "projects.0.description" for c in changes)

    def test_employers_and_dates_are_not_rewritable(self, profile):
        # Factual record. A rewrite quoting them cannot be located, so it is dropped.
        changes = validate_changes(
            {"rewrites": [{"original": "Zeta Labs", "improved": "Zeta Labs Inc."}]}, profile
        )
        assert not any(c["kind"] == "bullet" for c in changes)

    def test_junk_output_yields_no_changes(self, profile):
        assert validate_changes({}, profile) == []
        assert validate_changes({"rewrites": "not a list"}, profile) == []

    def test_ids_are_contiguous(self, profile):
        changes = validate_changes(
            {
                "summary": "A summary",
                "skills_order": ["SQL", "Python"],
                "rewrites": [
                    {
                        "original": "Built internal reporting tools in Python",
                        "improved": "Built Python reporting services",
                    }
                ],
            },
            profile,
        )
        assert [c["id"] for c in changes] == [f"c{i}" for i in range(len(changes))]


class TestApplyChanges:
    def _changes(self, profile):
        return validate_changes(
            {
                "summary": "Backend engineer with Python and SQL.",
                "skills_order": ["SQL", "Python"],
                "rewrites": [
                    {
                        "original": "Built internal reporting tools in Python",
                        "improved": "Built Python reporting services",
                    }
                ],
            },
            profile,
        )

    def test_only_accepted_changes_are_applied(self, profile):
        changes = self._changes(profile)
        summary_id = next(c["id"] for c in changes if c["kind"] == "summary")

        tailored = apply_changes(profile, changes, [summary_id])
        assert tailored["summary"] == "Backend engineer with Python and SQL."
        # The rewrite was not accepted, so the bullet is untouched.
        assert tailored["experience"][0]["responsibilities"][0] == (
            "Built internal reporting tools in Python"
        )

    def test_accepting_a_rewrite_replaces_the_line(self, profile):
        changes = self._changes(profile)
        bullet_id = next(c["id"] for c in changes if c["kind"] == "bullet")

        tailored = apply_changes(profile, changes, [bullet_id])
        assert tailored["experience"][0]["responsibilities"][0] == (
            "Built Python reporting services"
        )

    def test_the_source_profile_is_never_mutated(self, profile):
        import copy

        before = copy.deepcopy(profile)
        changes = self._changes(profile)
        apply_changes(profile, changes, [c["id"] for c in changes])
        assert profile == before

    def test_accepting_nothing_returns_the_original(self, profile):
        assert apply_changes(profile, self._changes(profile), []) == profile

    def test_an_unknown_id_is_ignored(self, profile):
        assert apply_changes(profile, self._changes(profile), ["nope"]) == profile

    def test_a_stale_path_does_not_raise(self, profile):
        # The profile was edited between proposing and applying.
        changes = [
            {"id": "c0", "kind": "bullet", "path": "experience.9.responsibilities.3",
             "before": "x", "after": "y"}
        ]
        assert apply_changes(profile, changes, ["c0"]) == profile


class TestProposeOptimisations:
    async def test_unsupported_claims_never_reach_the_candidate(self, fake_llm, profile):
        fake_llm(
            "optimizer",
            {
                "summary": "Backend engineer with Python and SQL.",
                "rewrites": [
                    {
                        "original": "Built internal reporting tools in Python",
                        # Kubernetes appears nowhere in this profile.
                        "improved": "Built reporting tools on Kubernetes",
                    }
                ],
            },
        )
        result = await propose_optimisations(profile, "A posting", {})

        assert all("Kubernetes" not in c["after"] for c in result["changes"])
        assert result["rejected"][0]["fabricated"] == ["Kubernetes"]

    async def test_offered_ids_are_renumbered_after_screening(self, fake_llm, profile):
        fake_llm(
            "optimizer",
            {
                "summary": "Engineer using Kubernetes everywhere.",  # rejected
                "rewrites": [
                    {
                        "original": "Built internal reporting tools in Python",
                        "improved": "Built Python reporting services",
                    }
                ],
            },
        )
        result = await propose_optimisations(profile, "A posting", {})
        assert [c["id"] for c in result["changes"]] == ["c0"]

    async def test_a_model_failure_propagates(self, fake_llm, profile):
        fake_llm("optimizer", raises=llm.LLMTimeoutError("slow"))
        with pytest.raises(llm.LLMError):
            await propose_optimisations(profile, "A posting", {})

    async def test_the_posting_and_profile_reach_the_prompt(self, fake_llm, profile):
        calls = fake_llm("optimizer", {})
        await propose_optimisations(profile, "UNIQUE-POSTING-MARKER", {})
        assert "UNIQUE-POSTING-MARKER" in calls[0]
        assert "Zeta Labs" in calls[0]
