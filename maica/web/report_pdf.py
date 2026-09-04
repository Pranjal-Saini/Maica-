"""The analysis as a document a consultant can hand over.

The export used to be a JSON dump of everything stored, including every raw
uploaded row. That is an archive format — useful for moving data between
systems, useless to the person who has to tell a controller what happened.

This produces the other thing: what was uploaded, what it covers, what could
not be checked, and the records worth opening. It deliberately carries the
ingest summary, because an export read as the wrong type silently drops its
change columns and nothing else in the product says so loudly enough.

fpdf2 is pure Python, so this adds no system libraries to a Windows dev
machine or the Docker image — which ruled out the HTML-rendering engines that
would have produced prettier output.

Its built-in fonts are latin-1 only, so text is folded to that before it is
written. Western European accents survive intact; a euro sign or a CJK entity
name does not, and comes through decomposed or marked rather than crashing the
export. Embedding a Unicode TTF would fix it properly and is a font-licensing
decision, the same one static/fonts/README.md describes for the wordmark.
"""

import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from fpdf import FPDF

#: Typographic characters this codebase writes deliberately, mapped to the
#: ASCII the built-in fonts can render.
_PUNCTUATION = {
    "—": "-",
    "–": "-",
    "·": "-",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "…": "...",
}


def pdf_safe(text: str) -> str:
    """Folds text into what the built-in fonts can write.

    Client data can hold anything, and a document being handed to a controller
    must not fail to generate because an entity name carries a character the
    font lacks. Accented Latin survives; anything else is decomposed, and what
    will not decompose is marked rather than dropped, so a substitution is
    visible instead of silent.
    """
    for fancy, plain in _PUNCTUATION.items():
        text = text.replace(fancy, plain)
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        # Strip the combining marks NFKD produces, so an accent degrades to its
        # base letter. Without this a single euro sign anywhere in the string
        # sends it down this path and turns every "u" umlaut into "u?".
        decomposed = unicodedata.normalize("NFKD", text)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        text = stripped.encode("latin-1", "replace").decode("latin-1")
    return text


INK = (17, 19, 16)
BRAND = (56, 79, 255)
GREY = (110, 110, 110)


@dataclass(frozen=True)
class SourceSummary:
    """One uploaded file, as it was understood."""

    source_type: str
    rows_understood: int
    rows_skipped: int
    columns_ignored: list[str]


@dataclass(frozen=True)
class AnalysisReport:
    tenant_name: str
    analysis_id: str
    total_records: int
    records_with_change_evidence: int
    sources: list[SourceSummary]
    shortlist: list[tuple[str, str | None, str]]  # source_id, record_type, reason
    ranked_on: str


class _Doc(FPDF):
    def __init__(self, tenant_name: str) -> None:
        super().__init__()
        self._tenant_name = tenant_name
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        self.set_font("helvetica", "B", 9)
        self.set_text_color(*INK)
        self.cell(0, 6, "MAICA", new_x="LMARGIN", new_y="NEXT")
        self.set_font("helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 4, pdf_safe(self._tenant_name), new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("helvetica", "", 7)
        self.set_text_color(*GREY)
        self.cell(
            0,
            4,
            "Read-only. MAICA reads evidence and never writes to a NetSuite account."
            f"    -    page {self.page_no()}",
        )


def _heading(doc: _Doc, text: str) -> None:
    doc.ln(3)
    doc.set_font("helvetica", "B", 11)
    doc.set_text_color(*INK)
    doc.multi_cell(0, 6, pdf_safe(text), new_x="LMARGIN", new_y="NEXT")
    doc.ln(1)


def _body(doc: _Doc, text: str, *, grey: bool = False, size: float = 9) -> None:
    doc.set_font("helvetica", "", size)
    doc.set_text_color(*(GREY if grey else INK))
    doc.multi_cell(0, 4.6, pdf_safe(text), new_x="LMARGIN", new_y="NEXT")


def build_analysis_pdf(report: AnalysisReport) -> bytes:
    doc = _Doc(report.tenant_name)
    doc.add_page()

    doc.set_font("helvetica", "B", 17)
    doc.set_text_color(*INK)
    doc.multi_cell(0, 8, "Analysis summary", new_x="LMARGIN", new_y="NEXT")
    _body(
        doc,
        f"Analysis {report.analysis_id}\n"
        f"Generated {datetime.now(UTC).strftime('%d %b %Y %H:%M UTC')}",
        grey=True,
        size=8,
    )

    _heading(doc, "What was uploaded")
    if report.sources:
        for source in report.sources:
            counted = f"{source.rows_understood:,} rows understood, {source.rows_skipped:,} skipped"
            _body(doc, f"{source.source_type} — {counted}")
            if source.columns_ignored:
                # The line that matters: a file read as the wrong type shows up
                # here as its most useful columns sitting in "ignored".
                _body(
                    doc,
                    f"    columns ignored: {', '.join(source.columns_ignored)}",
                    grey=True,
                    size=8,
                )
    else:
        _body(doc, "No evidence has been uploaded to this analysis.", grey=True)

    _heading(doc, "What it covers")
    missing = report.total_records - report.records_with_change_evidence
    _body(doc, f"{report.total_records:,} records in this analysis.")
    if report.total_records:
        _body(
            doc,
            f"{report.records_with_change_evidence:,} carry change evidence"
            + (
                f"; the other {missing:,} appear only in snapshot evidence, so nothing "
                "here can say what changed on them."
                if missing
                else "."
            ),
            grey=True,
        )

    _heading(doc, "Records worth opening")
    _body(doc, report.ranked_on, grey=True, size=8)
    doc.ln(1)
    if report.shortlist:
        for index, (source_id, record_type, reason) in enumerate(report.shortlist, start=1):
            doc.set_font("helvetica", "B", 9)
            doc.set_text_color(*INK)
            doc.multi_cell(
                0,
                5,
                pdf_safe(f"{index}.  {source_id}   {record_type or 'unknown type'}"),
                new_x="LMARGIN",
                new_y="NEXT",
            )
            _body(doc, f"      {reason}", grey=True, size=8)
            doc.ln(0.5)
    else:
        _body(doc, "Nothing in this evidence stands out from the rest of the account.", grey=True)

    _heading(doc, "How to read this")
    _body(
        doc,
        "These records are the ones least like the rest of this account. Unusual is not the "
        "same as wrong, and nothing here is a statement that anything caused anything. Ranked "
        "contributing factors for a single transaction, with the evidence behind each, are in "
        "the record's own report.",
        grey=True,
        size=8,
    )

    return bytes(doc.output())
