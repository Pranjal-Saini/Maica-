from collections.abc import Callable

from maica.ingest.csv_saved_search import CsvSavedSearchSource
from maica.ingest.interface import IngestSource
from maica.ingest.system_notes import SystemNotesCsvSource

# Keyed by the evidence_type a caller selects — not the same as an
# IngestResult.source_type string, which each source sets on its own output.
INGEST_SOURCES: dict[str, Callable[[], IngestSource]] = {
    "saved_search_csv": CsvSavedSearchSource,
    "system_notes_csv": SystemNotesCsvSource,
}


def get_ingest_source(evidence_type: str) -> IngestSource | None:
    factory = INGEST_SOURCES.get(evidence_type)
    return factory() if factory is not None else None
