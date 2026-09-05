import heapq
from collections import defaultdict
from collections.abc import Sequence

import networkx as nx

from maica.graph.builder import RecordLike, field_value_node_id

#: Ids listed inline before the rest are summarised. Naming every record that
#: shares a value is quadratic in the size of the group: on a currency or
#: subsidiary column, one 4,000-record analysis rendered 139 MB in 18 seconds,
#: on the event loop, for any authenticated caller who asked.
MAX_SHARED_IDS = 10


def _sharers(graph: nx.Graph, node_id: str) -> tuple[list[str], int]:
    """The first few record ids on a value node, and how many there are.

    Computed once per value rather than once per record. Doing it per record
    walks every neighbour N times for a value held by N records, which is what
    made a currency column quadratic.
    """
    if not graph.has_node(node_id):
        return [], 0
    neighbours = [n.removeprefix("record:") for n in graph.neighbors(node_id)]
    # nsmallest, not sorted: only the ids that will be printed need ordering.
    return heapq.nsmallest(MAX_SHARED_IDS + 1, neighbours), len(neighbours)


def _shared_suffix(top: list[str], total: int, source_id: str) -> str:
    others = [candidate for candidate in top if candidate != source_id][:MAX_SHARED_IDS]
    remaining = total - 1 - len(others)  # -1 for this record itself
    if not others:
        return ""
    shown = ", ".join(others)
    if remaining > 0:
        return f" (shared with {shown} and {remaining} more)"
    return f" (shared with {shown})"


def render_text(graph: nx.Graph, records: Sequence[RecordLike]) -> str:
    """Renders one analysis's records and their graph relationships as plain
    text. Every field value for every record is listed; values that connect to
    other records via a shared field_value node are annotated with which other
    records they are shared with."""
    rows_by_source_id: dict[str, list[RecordLike]] = defaultdict(list)
    for record in records:
        rows_by_source_id[record.source_id].append(record)

    sharer_cache: dict[str, tuple[list[str], int]] = {}
    lines: list[str] = []
    for source_id in sorted(rows_by_source_id):
        rows = rows_by_source_id[source_id]
        record_type = rows[0].record_type or "(unknown type)"
        lines.append(f"Record {source_id} ({record_type})")

        for row in sorted(rows, key=lambda r: r.field_name):
            if not row.new_value:
                lines.append(f"  {row.field_name} = (empty)")
                continue

            node_id = field_value_node_id(row.field_name, row.new_value)
            if node_id not in sharer_cache:
                sharer_cache[node_id] = _sharers(graph, node_id)
            top, total = sharer_cache[node_id]
            suffix = _shared_suffix(top, total, source_id)
            lines.append(f"  {row.field_name} = {row.new_value!r}{suffix}")

        lines.append("")

    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"
