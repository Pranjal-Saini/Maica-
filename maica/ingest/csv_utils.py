import csv
import io
import re
from collections.abc import Iterator
from datetime import datetime

from maica.ingest.errors import IngestValidationError

DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"]


def decode_text(raw_input: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw_input.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestValidationError("could not decode file as text")


def sniff_dialect(text: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(text[:4096])
    except csv.Error:
        return csv.excel


def normalize_header(raw: str, alias_map: dict[str, str]) -> str:
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return alias_map.get(key, key)


def try_parse_date(value: str) -> str | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def build_dict_reader(text: str) -> csv.DictReader:
    dialect = sniff_dialect(text)
    return csv.DictReader(io.StringIO(text), dialect=dialect)


def score_header_row(raw_input: bytes, alias_map: dict[str, str]) -> int:
    """Counts how many of the file's header columns are names this alias map
    knows. Never raises — an undecodable or headerless file scores 0 — so it
    is safe to call speculatively on an unknown upload."""
    try:
        text = decode_text(raw_input)
    except IngestValidationError:
        return 0
    if not text.strip():
        return 0

    reader = build_dict_reader(text)
    if not reader.fieldnames:
        return 0

    return sum(
        1 for raw in reader.fieldnames if re.sub(r"\s+", " ", raw.strip().lower()) in alias_map
    )


def iter_rows(reader: csv.DictReader) -> Iterator[dict]:
    """Yields the reader's rows, turning a malformed file into a named gap.

    csv raises on a field over its 128 KB limit and on some quoting errors, and
    an uploaded export is untrusted input by definition — a 500 there tells the
    consultant nothing and looks like the tool broke rather than the file being
    unreadable.
    """
    try:
        yield from reader
    except csv.Error as exc:
        raise IngestValidationError(f"could not read this CSV: {exc}") from exc
