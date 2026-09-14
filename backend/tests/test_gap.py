"""
The skills gap.

The estimates here are the part worth protecting. "Learn Docker and gain 7%" is
trivially easy to make up, and a made-up number is worse than no number because
someone might spend a month acting on it. Each estimate re-runs the real
scoring rule with one more skill supported.
"""

from gap import analyse_gaps


def analysis(job_id, score, missing, evidenced, title="A role", company="A company"):
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "match_score": score,
        "missing_skills": missing,
        # Only the count matters to the scoring rule.
        "evidence": {f"skill{i}": "quote" for i in range(evidenced)},
    }


class TestAnalyseGaps:
    def test_no_analyses_yields_nothing(self):
        result = analyse_gaps([])
        assert result["gaps"] == []
        assert result["analysed"] == 0
        assert result["average_score"] is None

    def test_the_most_frequent_gap_ranks_first(self):
        result = analyse_gaps(
            [
                analysis(1, 60, ["Docker", "Kafka"], 4),
                analysis(2, 65, ["Docker"], 5),
                analysis(3, 55, ["Docker", "Terraform"], 3),
            ]
        )
        assert result["gaps"][0]["skill"] == "Docker"
        assert result["gaps"][0]["occurrences"] == 3
        assert result["gaps"][0]["share"] == 100

    def test_spellings_are_merged_case_insensitively(self):
        result = analyse_gaps(
            [
                analysis(1, 60, ["docker"], 4),
                analysis(2, 60, ["Docker"], 4),
                analysis(3, 60, ["DOCKER"], 4),
            ]
        )
        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["occurrences"] == 3
        # The capitalised spelling is the one a human would write.
        assert result["gaps"][0]["skill"] in {"Docker", "DOCKER"}

    def test_lift_is_averaged_over_every_analysis_not_only_affected_ones(self):
        """
        A skill missing from one posting in ten is worth less than one missing
        from nine, and the ranking has to reflect that.
        """
        common = [analysis(i, 60, ["Docker"], 4) for i in range(4)]
        rare = [analysis(99, 60, ["Erlang"], 4)]
        result = analyse_gaps(common + rare)

        docker = next(g for g in result["gaps"] if g["skill"] == "Docker")
        erlang = next(g for g in result["gaps"] if g["skill"] == "Erlang")
        assert docker["average_lift"] > erlang["average_lift"]

    def test_each_gap_names_the_postings_it_costs_you(self):
        result = analyse_gaps(
            [analysis(7, 60, ["Docker"], 4, title="Backend Engineer", company="Acme")]
        )
        posting = result["gaps"][0]["postings"][0]
        assert posting["job_id"] == 7
        assert posting["title"] == "Backend Engineer"
        assert posting["estimated_score"] >= posting["current_score"]

    def test_the_average_score_is_reported(self):
        result = analyse_gaps(
            [analysis(1, 40, ["A"], 2), analysis(2, 80, ["B"], 8)]
        )
        assert result["average_score"] == 60

    def test_the_projection_is_not_a_sum_of_individual_lifts(self):
        """
        Closing two gaps in the same posting overlaps. Adding the separate
        lifts together would overstate the result, sometimes wildly.
        """
        result = analyse_gaps([analysis(1, 50, ["Docker", "Kafka"], 3)])
        separate_sum = sum(g["average_lift"] for g in result["gaps"])
        actual = result["projected_average"] - result["average_score"]
        assert actual <= separate_sum + 0.01

    def test_the_projection_never_falls_below_the_current_average(self):
        result = analyse_gaps(
            [analysis(1, 70, ["Docker"], 6), analysis(2, 45, ["Kafka", "Go"], 2)]
        )
        assert result["projected_average"] >= result["average_score"]

    def test_a_posting_with_nothing_missing_contributes_no_gaps(self):
        result = analyse_gaps([analysis(1, 90, [], 9)])
        assert result["gaps"] == []
        assert result["average_score"] == 90

    def test_the_list_is_capped(self):
        many = [analysis(1, 50, [f"Skill{i}" for i in range(20)], 3)]
        assert len(analyse_gaps(many, top_n=5)["gaps"]) == 5

    def test_blank_skill_names_are_ignored(self):
        result = analyse_gaps([analysis(1, 60, ["", "  ", "Docker"], 4)])
        assert [g["skill"] for g in result["gaps"]] == ["Docker"]
