"""
Render a profile as a PDF an ATS can actually read.

A resume that looks beautiful and parses badly defeats the entire product, so
the constraints here are deliberate and all of them cost visual flair:

- **Single column.** Multi-column layouts are the most common reason a parser
  interleaves two unrelated lines into nonsense.
- **Real text, laid out with text.** No tables, no text boxes, no images. Every
  string is drawn as selectable text at a known position.
- **Base-14 fonts only.** Helvetica is present in every PDF reader and every
  extractor; an embedded subset of a decorative font is where character
  mangling starts.
- **Standard uppercase section headings.** Parsers look for EXPERIENCE,
  EDUCATION, SKILLS. A heading called "Where I've Been" is invisible to them.
- **Bullets as a plain hyphen plus text**, not as list markup and not as a
  typographic bullet, which base-14 fonts cannot draw.

The output is verified by re-extracting it: if PyMuPDF cannot read the text
back out, neither can an ATS.
"""

from __future__ import annotations

from typing import Any

import pymupdf

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 in points
MARGIN = 54
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)
BOTTOM_LIMIT = PAGE_HEIGHT - MARGIN

BODY_FONT = "helv"
BOLD_FONT = "hebo"

NAME_SIZE = 17
HEADING_SIZE = 10
BODY_SIZE = 9.5
LINE_HEIGHT = 12.5


class _Canvas:
    """A cursor over a growing document, with page breaks handled for you."""

    def __init__(self) -> None:
        self.document = pymupdf.open()
        self.page = self.document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.y = MARGIN

    def _ensure_space(self, needed: float) -> None:
        if self.y + needed > BOTTOM_LIMIT:
            self.page = self.document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            self.y = MARGIN

    def text(
        self,
        content: str,
        *,
        size: float = BODY_SIZE,
        bold: bool = False,
        indent: float = 0,
        gap: float = 0,
    ) -> None:
        """Draw wrapped text, breaking pages as needed."""
        if not content or not content.strip():
            return

        font = BOLD_FONT if bold else BODY_FONT
        width = CONTENT_WIDTH - indent

        for line in _wrap(sanitise(content).strip(), font, size, width):
            self._ensure_space(LINE_HEIGHT)
            self.page.insert_text(
                (MARGIN + indent, self.y + size),
                line,
                fontname=font,
                fontsize=size,
            )
            self.y += max(LINE_HEIGHT, size * 1.3)

        self.y += gap

    def heading(self, title: str) -> None:
        self._ensure_space(34)
        self.y += 8
        self.page.insert_text(
            (MARGIN, self.y + HEADING_SIZE),
            title.upper(),
            fontname=BOLD_FONT,
            fontsize=HEADING_SIZE,
        )
        self.y += HEADING_SIZE + 4
        # A hairline under the heading. Drawn as a line, never as a bordered
        # table cell, which some parsers treat as a layout boundary.
        self.page.draw_line(
            pymupdf.Point(MARGIN, self.y),
            pymupdf.Point(PAGE_WIDTH - MARGIN, self.y),
            color=(0.7, 0.7, 0.7),
            width=0.6,
        )
        self.y += 7

    def bullet(self, content: str) -> None:
        if not content.strip():
            return
        font, size = BODY_FONT, BODY_SIZE
        lines = _wrap(sanitise(content).strip(), font, size, CONTENT_WIDTH - 12)
        for index, line in enumerate(lines):
            self._ensure_space(LINE_HEIGHT)
            prefix = "- " if index == 0 else "  "
            self.page.insert_text(
                (MARGIN + (0 if index == 0 else 12), self.y + size),
                f"{prefix}{line}" if index == 0 else line,
                fontname=font,
                fontsize=size,
            )
            self.y += LINE_HEIGHT

    def to_bytes(self) -> bytes:
        return self.document.tobytes()

    def close(self) -> None:
        self.document.close()


# Typographic characters a model emits freely and a base-14 font cannot draw.
# Left alone they come out as replacement glyphs - a cover letter reading
# "Zoho<?>s team" is worse than one with a straight apostrophe.
_TYPOGRAPHIC = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "–": "-", "—": "-", "‒": "-", "―": "-",
        "…": "...", "•": "-", "·": "-",
        " ": " ", " ": " ", " ": " ", "​": "",
        "′": "'", "″": '"', "«": '"', "»": '"',
    }
)


def sanitise(text: str) -> str:
    """
    Make text drawable by a base-14 font.

    Smart quotes and dashes are folded to their ASCII equivalents; anything
    still outside Latin-1 is dropped rather than drawn as a replacement box,
    because a missing character reads as a typo and a box reads as broken
    software.
    """
    folded = (text or "").translate(_TYPOGRAPHIC)
    return "".join(char for char in folded if char == "\n" or ord(char) < 256)


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Greedy word wrap measured against the real font metrics."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pymupdf.get_text_length(candidate, fontname=font, fontsize=size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _contact_line(profile: dict[str, Any]) -> str:
    links = profile.get("links") or {}
    parts = [
        profile.get("email"),
        profile.get("phone"),
        profile.get("location"),
        links.get("github"),
        links.get("linkedin"),
        links.get("portfolio"),
    ]
    return "  |  ".join(str(part).strip() for part in parts if str(part or "").strip())


def render(profile: dict[str, Any]) -> bytes:
    """Render a profile to PDF bytes."""
    canvas = _Canvas()
    try:
        name = (profile.get("name") or "").strip()
        if name:
            canvas.text(name, size=NAME_SIZE, bold=True)
        contact = _contact_line(profile)
        if contact:
            canvas.text(contact, size=BODY_SIZE - 0.5, gap=2)

        summary = (profile.get("summary") or "").strip()
        if summary:
            canvas.heading("Summary")
            canvas.text(summary)

        skills = [s for s in (profile.get("skills") or []) if str(s).strip()]
        if skills:
            canvas.heading("Skills")
            canvas.text(", ".join(str(skill).strip() for skill in skills))

        experience = [e for e in (profile.get("experience") or []) if isinstance(e, dict)]
        if any(e.get("company") or e.get("designation") for e in experience):
            canvas.heading("Experience")
            for entry in experience:
                title = " - ".join(
                    part
                    for part in (
                        str(entry.get("designation") or "").strip(),
                        str(entry.get("company") or "").strip(),
                    )
                    if part
                )
                if title:
                    canvas.text(title, bold=True)
                duration = str(entry.get("duration") or "").strip()
                if duration:
                    canvas.text(duration, size=BODY_SIZE - 0.5)
                for line in (entry.get("responsibilities") or []) + (
                    entry.get("achievements") or []
                ):
                    if isinstance(line, str):
                        canvas.bullet(line)
                canvas.y += 4

        projects = [p for p in (profile.get("projects") or []) if isinstance(p, dict)]
        if any(p.get("name") for p in projects):
            canvas.heading("Projects")
            for entry in projects:
                heading = str(entry.get("name") or "").strip()
                if heading:
                    canvas.text(heading, bold=True)
                description = str(entry.get("description") or "").strip()
                if description:
                    canvas.text(description)
                technologies = [
                    str(tech).strip()
                    for tech in (entry.get("technologies") or [])
                    if str(tech).strip()
                ]
                if technologies:
                    canvas.text(f"Technologies: {', '.join(technologies)}",
                                size=BODY_SIZE - 0.5)
                for link_field in ("github", "live_demo"):
                    link = str(entry.get(link_field) or "").strip()
                    if link:
                        canvas.text(link, size=BODY_SIZE - 0.5)
                canvas.y += 4

        education = [e for e in (profile.get("education") or []) if isinstance(e, dict)]
        if any(e.get("degree") or e.get("college") for e in education):
            canvas.heading("Education")
            for entry in education:
                line = " - ".join(
                    part
                    for part in (
                        str(entry.get("degree") or "").strip(),
                        str(entry.get("college") or "").strip(),
                        str(entry.get("year") or "").strip(),
                    )
                    if part
                )
                if line:
                    canvas.text(line)

        certifications = [
            str(item).strip()
            for item in (profile.get("certifications") or [])
            if str(item).strip()
        ]
        if certifications:
            canvas.heading("Certifications")
            for item in certifications:
                canvas.bullet(item)

        languages = [
            str(item).strip()
            for item in (profile.get("languages") or [])
            if str(item).strip()
        ]
        if languages:
            canvas.heading("Languages")
            canvas.text(", ".join(languages))

        return canvas.to_bytes()
    finally:
        canvas.close()


def render_letter(content: str, *, name: str = "") -> bytes:
    """
    Render a cover letter as a plain PDF.

    Same constraints as the resume and for the same reason: many employers run
    the letter through the same parser, and a letter that arrives as unreadable
    glyphs is worse than no letter.
    """
    canvas = _Canvas()
    try:
        if name.strip():
            canvas.text(name.strip(), size=NAME_SIZE - 3, bold=True, gap=6)

        for paragraph in (content or "").split("\n\n"):
            canvas.text(paragraph.strip(), gap=8)

        return canvas.to_bytes()
    finally:
        canvas.close()


def extract_text(pdf_bytes: bytes) -> str:
    """Read the text back out - the same way an ATS would."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        return "\n".join(page.get_text("text") for page in document).strip()
