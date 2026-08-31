from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

import networkx as nx

_RECORD_PREFIX = "record"
_FIELD_VALUE_PREFIX = "field_value"


class RecordLike(Protocol):
    """Structural type so this module (and reasoning/) depends on neither the
    SQLAlchemy Record model nor NormalizedRecordDraft specifically — both
    satisfy it."""

    source_id: str
    record_type: str | None
    field_name: str
    old_value: str | None
    new_value: str | None
    actor: str | None
    context: str | None
    occurred_at: datetime | None


def record_node_id(source_id: str) -> str:
    return f"{_RECORD_PREFIX}:{source_id}"


def field_value_node_id(field_name: str, value: str) -> str:
    return f"{_FIELD_VALUE_PREFIX}:{field_name}={value}"


def build_dependency_graph(records: Sequence[RecordLike]) -> nx.Graph:
    """Builds an undirected graph over one analysis's normalized records.

    Record nodes represent one NetSuite record (by source_id). Field-value
    nodes represent one field/value pair shared by two or more distinct
    records — a candidate relationship point (same account, same entity, same
    actor...). A value held by only one record is not a relationship and is
    left out, so the graph reflects connections rather than a full data dump.

    This makes no claim about causation or a true script/workflow dependency —
    that requires evidence this ingestion path does not yet have (see
    ingestion.md). It only represents which records share which field values.
    """
    graph: nx.Graph = nx.Graph()

    source_ids_by_value: dict[tuple[str, str], set[str]] = defaultdict(set)
    record_type_by_source_id: dict[str, str | None] = {}

    for record in records:
        record_type_by_source_id.setdefault(record.source_id, record.record_type)
        if record.new_value:
            source_ids_by_value[(record.field_name, record.new_value)].add(record.source_id)

    for source_id, record_type in record_type_by_source_id.items():
        graph.add_node(
            record_node_id(source_id),
            kind="record",
            source_id=source_id,
            record_type=record_type,
        )

    for (field_name, value), source_ids in source_ids_by_value.items():
        if len(source_ids) < 2:
            continue
        node_id = field_value_node_id(field_name, value)
        graph.add_node(node_id, kind="field_value", field_name=field_name, value=value)
        for source_id in source_ids:
            graph.add_edge(record_node_id(source_id), node_id, field_name=field_name)

    return graph
