from pathlib import Path

from maica.ingest.system_notes import SystemNotesCsvSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_clean_export_all_rows_understood() -> None:
    result = SystemNotesCsvSource().ingest((FIXTURES / "system_notes_clean.csv").read_bytes())

    assert result.rows_understood == 3
    assert result.rows_skipped == 0
    assert result.skip_reasons == []
    assert result.unavailable_reason is None
    assert result.rows[0]["field_name"] == "Amount"
    assert result.rows[0]["old_value"] == "1500.00"
    assert result.rows[0]["new_value"] == "1800.00"
    assert result.rows[0]["actor"] == "jsmith"
    assert result.rows[0]["context"] == "UIF"
    assert result.rows[0]["occurred_at"] == "2026-01-20T00:00:00"


def test_messy_export_tolerates_renamed_headers_missing_id_and_missing_field() -> None:
    result = SystemNotesCsvSource().ingest((FIXTURES / "system_notes_messy.csv").read_bytes())

    assert result.rows_understood == 2
    assert result.rows_skipped == 2
    assert any("no identifying column" in reason for reason in result.skip_reasons)
    assert any("no field name" in reason for reason in result.skip_reasons)
    assert any("unparsed date" in reason for reason in result.skip_reasons)
    assert "custom note" in result.columns_ignored


def test_empty_file_reports_unavailable() -> None:
    result = SystemNotesCsvSource().ingest(b"")
    assert result.unavailable_reason == "uploaded file was empty"


def test_no_recognizable_rows_reports_unavailable() -> None:
    result = SystemNotesCsvSource().ingest(b"Foo,Bar\n1,2\n")
    assert result.rows == []
    assert result.unavailable_reason == "no recognizable system notes rows found"
