"""Contract test any IngestSource implementation must satisfy — reused later
for the Path B NetSuite/SuiteQL adapter."""

from maica.ingest.csv_saved_search import CsvSavedSearchSource
from maica.ingest.interface import IngestResult, IngestSource


def _assert_satisfies_ingest_contract(source: IngestSource, raw_input: bytes) -> None:
    result = source.ingest(raw_input)

    assert isinstance(result, IngestResult)
    assert result.request.source_type
    assert result.request.requested_at is not None
    assert result.rows_understood == len(result.rows)
    assert result.rows_understood >= 0
    assert result.rows_skipped >= 0
    if not result.rows:
        assert result.unavailable_reason is not None


def test_csv_saved_search_source_satisfies_contract() -> None:
    _assert_satisfies_ingest_contract(CsvSavedSearchSource(), b"Internal ID,Date\n1,1/1/2026\n")


def test_csv_saved_search_source_satisfies_contract_on_empty_input() -> None:
    _assert_satisfies_ingest_contract(CsvSavedSearchSource(), b"")
