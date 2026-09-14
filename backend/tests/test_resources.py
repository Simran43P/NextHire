"""
Links for a missing skill.

The rule that matters: never guess a URL. A broken link in a tool that exists
to be trusted costs more than the convenience is worth, so there are only two
kinds here - a project's own documentation, curated by hand, and a search,
which cannot 404.
"""

import resources


class TestForSkill:
    def test_a_curated_skill_gets_its_official_docs(self):
        links = resources.for_skill("Docker")
        assert links[0]["kind"] == "docs"
        assert links[0]["url"] == "https://docs.docker.com/"

    def test_matching_is_case_insensitive(self):
        assert resources.for_skill("KUBERNETES")[0]["kind"] == "docs"

    def test_an_unknown_skill_still_gets_a_search(self):
        links = resources.for_skill("Cobol")
        assert len(links) == 1
        assert links[0]["kind"] == "search"
        assert "Cobol" in links[0]["url"] or "Cobol" in links[0]["label"]

    def test_every_skill_gets_at_least_one_link(self):
        for skill in ("Docker", "Fortran", "some in-house framework"):
            assert resources.for_skill(skill)

    def test_a_phrase_around_a_known_skill_still_matches(self):
        # Postings say "Docker containers" and "advanced SQL", not bare nouns.
        assert resources.for_skill("Docker containers")[0]["kind"] == "docs"
        assert resources.for_skill("advanced SQL")[0]["kind"] == "docs"

    def test_a_substring_of_an_unrelated_word_does_not_match(self):
        # "Go" must not match "Google Analytics" or "Django".
        assert resources.for_skill("Google Analytics")[0]["kind"] == "search"

    def test_blank_input_yields_nothing(self):
        assert resources.for_skill("") == []
        assert resources.for_skill("   ") == []

    def test_every_curated_url_is_absolute_and_https(self):
        for label, url in resources.OFFICIAL_DOCS.values():
            assert url.startswith("https://"), url
            assert label.strip()

    def test_search_urls_are_escaped(self):
        link = resources.for_skill("C++ & templates")[-1]
        assert " " not in link["url"]
        assert link["url"].startswith("https://")
