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

AUTO_DETECT = "auto"

# A file must match at least this many of a source's known column names before
# we'll claim it as that type. Below this it's reported as unrecognised rather
# than guessed at — a wrong guess would silently normalize evidence into the
# wrong shape, which is worse than saying "I don't know what this is".
_MIN_CONFIDENT_SCORE = 2


def get_ingest_source(evidence_type: str) -> IngestSource | None:
    factory = INGEST_SOURCES.get(evidence_type)
    return factory() if factory is not None else None


def detect_evidence_type(raw_input: bytes) -> str | None:
    """Picks the evidence type whose known column names best match this file's
    header row. Returns None when nothing matches confidently enough, or when
    two types tie — the caller should then report the file as unrecognised
    instead of guessing."""
    scores = {
        evidence_type: factory().header_match_score(raw_input)
        for evidence_type, factory in INGEST_SOURCES.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score < _MIN_CONFIDENT_SCORE:
        return None

    winners = [name for name, score in scores.items() if score == best_score]
    if len(winners) != 1:
        return None
    return winners[0]
