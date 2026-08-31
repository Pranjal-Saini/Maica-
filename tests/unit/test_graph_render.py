from pathlib import Path
from uuid import uuid4

from maica.evidence.models import RawEvidence
from maica.evidence.normalizer import SavedSearchCsvNormalizer
from maica.graph.builder import build_dependency_graph
from maica.graph.render import render_text
from maica.ingest.csv_saved_search import CsvSavedSearchSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_render_text_lists_every_field_and_annotates_shared_ones() -> None:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    ingest_result = CsvSavedSearchSource().ingest(csv_bytes)
    raw_evidence = RawEvidence(
        id=uuid4(),
        tenant_id=uuid4(),
        analysis_id=uuid4(),
        source_type=ingest_result.request.source_type,
        request_made=ingest_result.request.request_detail,
        payload={"rows": ingest_result.rows},
        understood_summary={},
        unavailable_reason=ingest_result.unavailable_reason,
    )
    drafts, _ = SavedSearchCsvNormalizer().normalize(raw_evidence)
    graph = build_dependency_graph(drafts)

    text = render_text(graph, drafts)

    assert "Record 1001 (Journal Entry)" in text
    assert "Record 1003 (Invoice)" in text
    assert "entity = 'Acme Corp' (shared with 1002)" in text
    assert "account = '4000 - Revenue' (shared with 1003)" in text
    # amount is unique per row and should render with no "shared with" suffix
    assert "amount = '1500.00'\n" in text


def test_render_text_of_empty_records_is_empty() -> None:
    graph = build_dependency_graph([])
    assert render_text(graph, []) == ""
