"""
The ATS-safe PDF.

A resume that renders beautifully and parses badly defeats the entire product,
so these tests check the thing that actually matters: that the text can be read
back out. Every assertion below is written against extracted text rather than
against the drawing calls, because extraction is what an ATS does.
"""

import pymupdf

import resume_pdf


class TestSanitise:
    """
    Base-14 fonts cannot draw typographic characters, and a model emits them
    freely. Left alone they come out as replacement glyphs - a cover letter
    reading "Zoho<?>s team" looks like broken software.
    """

    def test_smart_quotes_and_dashes_become_ascii(self):
        text = resume_pdf.extract_text(
            resume_pdf.render_letter("Zoho’s team — “quoted”… ok.")
        )
        assert text == "Zoho's team - \"quoted\"... ok."
        assert "�" not in text

    def test_undrawable_characters_are_dropped_not_boxed(self):
        # A missing character reads as a typo; a replacement box reads as a bug.
        text = resume_pdf.extract_text(resume_pdf.render_letter("Hello 世界 world"))
        assert "�" not in text
        assert "Hello" in text and "world" in text

    def test_bullets_render_without_a_typographic_glyph(self):
        profile = {
            "name": "Asha",
            "experience": [{"company": "Zeta", "responsibilities": ["Did a thing"]}],
        }
        text = resume_pdf.extract_text(resume_pdf.render(profile))
        assert "- Did a thing" in text
        assert "�" not in text


class TestRender:
    def test_the_output_is_a_pdf(self, sample_profile):
        assert resume_pdf.render(sample_profile).startswith(b"%PDF-")

    def test_every_field_survives_extraction(self, sample_profile):
        text = resume_pdf.extract_text(resume_pdf.render(sample_profile))

        assert "Asha Menon" in text
        assert "asha.menon@example.com" in text
        assert "Python" in text and "FastAPI" in text
        assert "Resume Ranker" in text
        assert "CUSAT" in text
        assert "AWS Cloud Practitioner" in text

    def test_standard_section_headings_are_present(self, sample_profile):
        # Parsers look for these words. A heading called "Where I've Been" is
        # invisible to them.
        text = resume_pdf.extract_text(resume_pdf.render(sample_profile))
        for heading in ("SKILLS", "PROJECTS", "EDUCATION", "CERTIFICATIONS"):
            assert heading in text, f"{heading} is missing"

    def test_a_summary_is_rendered_when_present(self, sample_profile):
        tailored = {**sample_profile, "summary": "Backend engineer with Python."}
        text = resume_pdf.extract_text(resume_pdf.render(tailored))
        assert "SUMMARY" in text
        assert "Backend engineer with Python." in text

    def test_experience_bullets_survive(self):
        profile = {
            "name": "Asha",
            "experience": [
                {
                    "company": "Zeta Labs",
                    "designation": "Intern",
                    "duration": "2024",
                    "responsibilities": ["Built internal reporting tools in Python"],
                    "achievements": ["Cut report runtime by 40%"],
                }
            ],
        }
        text = resume_pdf.extract_text(resume_pdf.render(profile))
        assert "EXPERIENCE" in text
        assert "Zeta Labs" in text
        assert "Built internal reporting tools in Python" in text
        assert "Cut report runtime by 40%" in text

    def test_long_text_wraps_rather_than_running_off_the_page(self):
        sentence = "Built and operated a distributed reporting service in Python. " * 12
        profile = {
            "name": "Asha",
            "experience": [{"company": "Zeta", "responsibilities": [sentence.strip()]}],
        }
        pdf = resume_pdf.render(profile)

        with pymupdf.open(stream=pdf, filetype="pdf") as document:
            for page in document:
                for block in page.get_text("blocks"):
                    # No drawn text may extend past the right margin.
                    assert block[2] <= page.rect.width - 40

    def test_a_very_long_profile_spills_onto_more_pages(self):
        profile = {
            "name": "Asha",
            "experience": [
                {
                    "company": f"Company {index}",
                    "designation": "Engineer",
                    "duration": "2020-2024",
                    "responsibilities": [f"Did a considerable amount of work, item {index}"] * 6,
                }
                for index in range(12)
            ],
        }
        with pymupdf.open(stream=resume_pdf.render(profile), filetype="pdf") as document:
            assert document.page_count > 1

    def test_an_empty_profile_still_renders(self):
        # Nothing to say is not a crash.
        assert resume_pdf.render({}).startswith(b"%PDF-")

    def test_empty_sections_are_omitted_rather_than_left_as_bare_headings(self):
        text = resume_pdf.extract_text(
            resume_pdf.render({"name": "Asha", "skills": [], "experience": [], "projects": []})
        )
        assert "SKILLS" not in text
        assert "EXPERIENCE" not in text

    def test_rendering_is_deterministic_in_content(self, sample_profile):
        first = resume_pdf.extract_text(resume_pdf.render(sample_profile))
        second = resume_pdf.extract_text(resume_pdf.render(sample_profile))
        assert first == second

    def test_the_document_uses_only_base_14_fonts(self, sample_profile):
        # An embedded subset of a decorative font is where character mangling
        # starts; Helvetica is present in every reader and every extractor.
        with pymupdf.open(stream=resume_pdf.render(sample_profile), filetype="pdf") as doc:
            for page in doc:
                for font in page.get_fonts():
                    assert font[3].startswith("Helvetica"), font

    def test_there_are_no_images(self, sample_profile):
        # Text inside an image is text an ATS cannot read.
        with pymupdf.open(stream=resume_pdf.render(sample_profile), filetype="pdf") as doc:
            for page in doc:
                assert page.get_images() == []

    def test_the_layout_is_a_single_column(self, sample_profile):
        """
        Every text block starts at the same left edge.

        Multi-column layouts are the most common reason a parser interleaves two
        unrelated lines into nonsense, and the only reliable defence is not
        having a second column.
        """
        with pymupdf.open(stream=resume_pdf.render(sample_profile), filetype="pdf") as doc:
            lefts = {
                round(block[0])
                for page in doc
                for block in page.get_text("blocks")
                if block[4].strip()
            }
        # Body text and bullet continuations only; nothing near the page centre.
        assert max(lefts) < 100, lefts
