from pathlib import Path
from uuid import uuid4

from maica.evidence.models import RawEvidence
from maica.evidence.normalizer import NormalizedRecordDraft, SavedSearchCsvNormalizer
from maica.graph.builder import build_dependency_graph, field_value_node_id, record_node_id
from maica.ingest.csv_saved_search import CsvSavedSearchSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _drafts_from_clean_fixture() -> list[NormalizedRecordDraft]:
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
    return drafts


def test_shared_field_values_create_connecting_nodes() -> None:
    # clean fixture: 1001 & 1002 share entity "Acme Corp"; 1001 & 1003 share
    # account "4000 - Revenue"; 1002's account and everyone's amount/memo are
    # unique and should not appear as field_value nodes.
    drafts = _drafts_from_clean_fixture()

    graph = build_dependency_graph(drafts)

    assert graph.has_node(field_value_node_id("entity", "Acme Corp"))
    assert graph.has_node(field_value_node_id("account", "4000 - Revenue"))
    assert not graph.has_node(field_value_node_id("account", "2100 - AP"))
    assert not graph.has_node(field_value_node_id("amount", "1500.00"))

    assert graph.has_edge(record_node_id("1001"), field_value_node_id("entity", "Acme Corp"))
    assert graph.has_edge(record_node_id("1002"), field_value_node_id("entity", "Acme Corp"))
    assert not graph.has_edge(record_node_id("1003"), field_value_node_id("entity", "Acme Corp"))


def test_record_nodes_carry_record_type() -> None:
    drafts = _drafts_from_clean_fixture()

    graph = build_dependency_graph(drafts)

    assert graph.nodes[record_node_id("1001")]["record_type"] == "Journal Entry"
    assert graph.nodes[record_node_id("1003")]["record_type"] == "Invoice"


def test_empty_records_produce_empty_graph() -> None:
    graph = build_dependency_graph([])

    assert graph.number_of_nodes() == 0
