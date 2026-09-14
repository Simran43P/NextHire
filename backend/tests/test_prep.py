"""
Cover letters and interview preparation.

The cover letter cannot be screened the way tailored edits are - it is one
piece of prose, and discarding it over a single sentence would leave the
candidate with nothing. So the guarantee here is different: every unsupported
claim is *located*, and located again on save, because the candidate can type
one in themselves.
"""

import pytest

import llm
from cover_letter import TONES, generate, locate_unsupported
from interview import shape

PASSWORD = "correct-horse-battery"


class TestLocateUnsupported:
    def test_a_letter_built_from_the_profile_is_clean(self, sample_profile):
        letter = (
            "I am applying for this role. My work has been in Python and SQL, "
            "including a project built with FastAPI."
        )
        assert locate_unsupported(letter, sample_profile) == []

    def test_an_invented_technology_is_located_to_its_sentence(self, sample_profile):
        letter = (
            "I have worked extensively in Python. "
            "I also ran production Kubernetes clusters at scale."
        )
        flagged = locate_unsupported(letter, sample_profile)
        assert len(flagged) == 1
        assert "Kubernetes" in flagged[0]["claims"]
        # The sentence, not just the word: far more actionable to rewrite.
        assert "Kubernetes clusters" in flagged[0]["sentence"]

    def test_an_invented_number_is_caught(self, sample_profile):
        flagged = locate_unsupported("I cut latency by 60 percent.", sample_profile)
        assert flagged and "60" in flagged[0]["claims"]

    def test_several_bad_sentences_are_all_reported(self, sample_profile):
        letter = (
            "I use Python daily. "
            "I led a team at Infosys. "
            "I deploy with Kubernetes."
        )
        assert len(locate_unsupported(letter, sample_profile)) == 2

    def test_an_empty_letter_is_not_flagged(self, sample_profile):
        assert locate_unsupported("", sample_profile) == []

    def test_the_employer_being_written_to_is_not_a_claim(self, sample_profile):
        """
        Found against the real model: every letter flagged its own opening line
        because it named the company. A warning that fires every time is a
        warning nobody reads, and it would bury the ones that matter.
        """
        letter = "I am writing about the Python Developer role at Zoho."
        job = {"company": "Zoho", "title": "Python Developer"}

        assert locate_unsupported(letter, sample_profile) != []
        assert locate_unsupported(letter, sample_profile, job) == []

    def test_the_posting_does_not_launder_a_skill_claim(self, sample_profile):
        # Wanting Kubernetes is not evidence of having it, so the description
        # stays out of the corpus even though the company name goes in.
        job = {
            "company": "Zoho",
            "title": "Python Developer",
            "description": "We need Kubernetes and Terraform experience.",
        }
        flagged = locate_unsupported(
            "I have deep Kubernetes experience.", sample_profile, job
        )
        assert flagged and "Kubernetes" in flagged[0]["claims"]


class TestGenerate:
    async def test_a_clean_letter_comes_back_unflagged(self, fake_llm, sample_profile):
        fake_llm(
            "cover_letter",
            {"letter": "I work in Python and SQL.\n\nI built a project with FastAPI."},
        )
        result = await generate(sample_profile, {"title": "Dev"}, {}, "professional")

        assert result["unsupported"] == []
        assert result["word_count"] > 0
        assert result["tone"] == "professional"

    async def test_an_overreaching_letter_is_returned_with_its_claims_located(
        self, fake_llm, sample_profile
    ):
        fake_llm("cover_letter", {"letter": "I have deep Kubernetes experience."})
        result = await generate(sample_profile, {"title": "Dev"}, {})

        # Returned, not discarded - the candidate needs something to edit.
        assert result["letter"]
        assert result["unsupported"][0]["claims"] == ["Kubernetes"]

    async def test_an_unknown_tone_falls_back(self, fake_llm, sample_profile):
        fake_llm("cover_letter", {"letter": "Hello."})
        result = await generate(sample_profile, {}, {}, tone="interpretive-dance")
        assert result["tone"] in TONES

    async def test_malformed_output_yields_an_empty_letter_not_a_crash(
        self, fake_llm, sample_profile
    ):
        fake_llm("cover_letter", {"unexpected": "shape"})
        result = await generate(sample_profile, {}, {})
        assert result["letter"] == ""

    async def test_a_model_failure_propagates(self, fake_llm, sample_profile):
        fake_llm("cover_letter", raises=llm.LLMUnavailableError("down"))
        with pytest.raises(llm.LLMError):
            await generate(sample_profile, {}, {})


class TestInterviewShape:
    def test_the_three_groups_are_always_present(self):
        result = shape({})
        assert set(result) == {"technical", "behavioural", "gaps"}
        assert all(isinstance(value, list) for value in result.values())

    def test_gap_questions_keep_what_they_probe(self):
        result = shape(
            {"gaps": [{"question": "Tell me about Docker.", "probes": "Docker"}]}
        )
        assert result["gaps"][0]["probes"] == "Docker"

    def test_a_bare_string_gap_is_accepted(self):
        result = shape({"gaps": ["What is your Docker experience?"]})
        assert result["gaps"][0]["question"].startswith("What")
        assert result["gaps"][0]["probes"] == ""

    def test_duplicate_questions_collapse(self):
        result = shape({"gaps": ["Same question?", "same question?"]})
        assert len(result["gaps"]) == 1

    def test_groups_are_capped(self):
        result = shape({"technical": [f"Question {i}?" for i in range(30)]})
        assert len(result["technical"]) <= 6

    def test_junk_is_dropped_rather_than_raising(self):
        result = shape({"technical": [None, 5, "", "A real question?"], "gaps": [None, 7]})
        assert result["technical"] == ["5", "A real question?"] or "A real question?" in result["technical"]
        assert result["gaps"] == []

    def test_non_dict_input_is_survivable(self):
        assert shape("nonsense") == {"technical": [], "behavioural": [], "gaps": []}


@pytest.fixture
def mock_prep(monkeypatch):
    def install(*, letter=None, questions=None, raises=None):
        async def _letter(profile, job, analysis, tone="professional"):
            if raises:
                raise raises
            return letter or {
                "letter": "I work in Python.",
                "tone": tone,
                "unsupported": [],
                "word_count": 4,
            }

        async def _questions(profile, job, analysis):
            if raises:
                raise raises
            return questions or {
                "technical": ["How do you use Python?"],
                "behavioural": ["Tell me about a setback."],
                "gaps": [{"question": "Docker experience?", "probes": "Docker"}],
            }

        monkeypatch.setattr("routers.prep.cover_letter_service.generate", _letter)
        monkeypatch.setattr("routers.prep.interview_service.generate", _questions)

    return install


class TestRoutes:
    def test_a_guest_can_get_a_cover_letter(
        self, client, mock_prep, sample_profile, sample_job_description
    ):
        mock_prep()
        response = client.post(
            "/api/cover-letter",
            json={
                "profile": sample_profile,
                "job": {"title": "Dev", "description": sample_job_description},
            },
        )
        assert response.status_code == 200
        assert response.json()["letter"]
        assert response.json()["cover_letter_id"] is None

    def test_a_posting_with_no_description_is_rejected(
        self, client, mock_prep, sample_profile
    ):
        mock_prep()
        response = client.post(
            "/api/cover-letter",
            json={"profile": sample_profile, "job": {"title": "Dev", "description": ""}},
        )
        assert response.status_code == 400

    def test_a_letter_renders_to_pdf(self, client):
        response = client.post(
            "/api/cover-letter/pdf",
            json={"content": "Dear hiring manager,\n\nI am applying.", "name": "Asha"},
        )
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")

    def test_an_empty_letter_will_not_render(self, client):
        response = client.post("/api/cover-letter/pdf", json={"content": "   "})
        assert response.status_code == 400

    def test_interview_questions_come_back_grouped(
        self, client, mock_prep, sample_profile, sample_job_description
    ):
        mock_prep()
        response = client.post(
            "/api/interview-prep",
            json={
                "profile": sample_profile,
                "job": {"title": "Dev", "description": sample_job_description},
            },
        )
        assert response.status_code == 200
        questions = response.json()["questions"]
        assert questions["technical"] and questions["gaps"]

    def test_the_skills_gap_needs_an_account(self, client):
        assert client.get("/api/skills-gap").status_code == 401

    def test_the_skills_gap_is_empty_before_any_analysis(self, client, register):
        register()
        body = client.get("/api/skills-gap").json()
        assert body["gaps"] == []
        assert body["analysed"] == 0
