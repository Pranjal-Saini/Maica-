from collections import defaultdict
from collections.abc import Sequence

import networkx as nx

from maica.graph.builder import RecordLike, field_value_node_id, record_node_id


def render_text(graph: nx.Graph, records: Sequence[RecordLike]) -> str:
    """Renders one analysis's records and their graph relationships as plain
    text. Every field value for every record is listed; values that connect to
    other records via a shared field_value node are annotated with which other
    records they are shared with."""
    rows_by_source_id: dict[str, list[RecordLike]] = defaultdict(list)
    for record in records:
        rows_by_source_id[record.source_id].append(record)

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
            shared_with = sorted(
                neighbor.removeprefix("record:")
                for neighbor in (graph.neighbors(node_id) if graph.has_node(node_id) else [])
                if neighbor != record_node_id(source_id)
            )
            suffix = f" (shared with {', '.join(shared_with)})" if shared_with else ""
            lines.append(f"  {row.field_name} = {row.new_value!r}{suffix}")

        lines.append("")

    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"
