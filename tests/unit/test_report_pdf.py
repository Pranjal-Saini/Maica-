"""The PDF the analysis export produces.

fpdf2's built-in fonts are latin-1 only. Client data is not, so the fold has to
be exercised — a document being handed to a controller must not fail to
generate because an entity name carries a euro sign.
"""

from maica.web.report_pdf import AnalysisReport, SourceSummary, build_analysis_pdf, pdf_safe


def _report(**overrides) -> AnalysisReport:
    base = dict(
        tenant_name="Acme Corp",
        analysis_id="abc-123",
        total_records=4996,
        records_with_change_evidence=4572,
        sources=[SourceSummary("upload:system_notes_csv", 13, 0, [])],
        shortlist=[("4471", "Invoice", "Account changed by System")],
        ranked_on="Ranked on how unusual each record's changes are.",
    )
    return AnalysisReport(**{**base, **overrides})


def test_typographic_punctuation_becomes_something_the_font_can_write() -> None:
    assert pdf_safe("System \u2014 SCHEDULED \u00b7 2.2%") == "System - SCHEDULED - 2.2%"
    assert pdf_safe("record\u2019s changes") == "record's changes"


def test_western_european_accents_survive_intact() -> None:
    # latin-1 covers these, so a French or German entity name is unharmed.
    assert pdf_safe("Caf\u00e9 M\u00fcller Ltd") == "Caf\u00e9 M\u00fcller Ltd"


def test_a_character_the_font_lacks_does_not_take_the_accents_with_it() -> None:
    # One euro sign used to send the whole string down the fallback and turn
    # every umlaut into "u?". Accents now degrade to their base letter.
    folded = pdf_safe("\u00dcn\u00efcode \u20ac500 Ltd")

    assert folded.startswith("Unicode")
    folded.encode("latin-1")  # raises if the fold left anything unwritable


def test_a_pdf_is_produced_for_a_client_name_the_font_cannot_render() -> None:
    pdf = build_analysis_pdf(_report(tenant_name="\u6771\u4eac Trading \u20ac"))

    assert pdf.startswith(b"%PDF")


def test_the_report_names_columns_that_were_ignored() -> None:
    """The line that would have caught a System Notes file read as a saved
    search: its change columns show up sitting in "ignored"."""
    pdf = build_analysis_pdf(
        _report(
            sources=[
                SourceSummary("upload:saved_search_csv", 13, 0, ["old value", "set by", "context"])
            ]
        )
    )

    assert b"%PDF" in pdf[:8]
    assert len(pdf) > 1000


def test_an_empty_analysis_still_produces_a_document() -> None:
    pdf = build_analysis_pdf(
        _report(total_records=0, records_with_change_evidence=0, sources=[], shortlist=[])
    )

    assert pdf.startswith(b"%PDF")
