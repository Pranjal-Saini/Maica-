from pathlib import Path

from maica.ingest.csv_saved_search import CsvSavedSearchSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_clean_export_all_rows_understood() -> None:
    result = CsvSavedSearchSource().ingest(_load("saved_search_clean.csv"))

    assert result.rows_understood == 3
    assert result.rows_skipped == 0
    assert result.skip_reasons == []
    assert result.unavailable_reason is None
    assert "internal_id" in result.columns_recognized
    assert "occurred_at" in result.columns_recognized
    assert result.rows[0]["occurred_at"] == "2026-01-15T00:00:00"


def test_messy_export_tolerates_renamed_headers_and_blank_rows() -> None:
    result = CsvSavedSearchSource().ingest(_load("saved_search_messy.csv"))

    assert result.rows_understood == 3
    assert result.rows_skipped == 1
    assert any("no identifying column" in reason for reason in result.skip_reasons)
    assert any("unparsed date" in reason for reason in result.skip_reasons)
    assert "custom field 1" in result.columns_ignored
    assert result.unavailable_reason is None


def test_empty_file_reports_unavailable() -> None:
    result = CsvSavedSearchSource().ingest(b"")

    assert result.rows == []
    assert result.unavailable_reason == "uploaded file was empty"


def test_no_recognizable_rows_reports_unavailable() -> None:
    result = CsvSavedSearchSource().ingest(b"Foo,Bar\n1,2\n3,4\n")

    assert result.rows == []
    assert result.unavailable_reason == "no recognizable saved-search rows found"
