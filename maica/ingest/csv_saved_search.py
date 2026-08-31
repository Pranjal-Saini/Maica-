import csv
import io
import re
from datetime import UTC, datetime

from maica.ingest.errors import IngestValidationError
from maica.ingest.interface import IngestRequestMeta, IngestResult, IngestSource

# Known NetSuite saved-search export header variants -> normalized field name.
# Extend this map as new export shapes are seen; unmapped columns are tolerated,
# not rejected — they land in columns_ignored.
_HEADER_ALIASES: dict[str, str] = {
    "internal id": "internal_id",
    "internalid": "internal_id",
    "internal_id": "internal_id",
    "doc number": "document_number",
    "document number": "document_number",
    "date": "occurred_at",
    "trandate": "occurred_at",
    "transaction date": "occurred_at",
    "type": "record_type",
    "transaction type": "record_type",
    "name": "entity",
    "entity": "entity",
    "amount": "amount",
    "account": "account",
    "memo": "memo",
    "created by": "actor",
    "last modified by": "actor",
}

# Identifying columns — a row missing all of these cannot be traced back to a
# NetSuite record later, so it is dropped rather than kept as unusable noise.
_IDENTIFYING_COLUMNS = {"internal_id", "document_number"}

_DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"]


def _normalize_header(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return _HEADER_ALIASES.get(key, key)


def _decode(raw_input: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw_input.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestValidationError("could not decode file as text")


def _try_parse_date(value: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


class CsvSavedSearchSource(IngestSource):
    """Parses a NetSuite saved-search CSV export. Tolerant of extra columns,
    renamed headers, blank rows, and partial/unparsed dates — nothing is
    silently dropped or guessed; unusable rows are named in skip_reasons."""

    def ingest(self, raw_input: bytes) -> IngestResult:
        request = IngestRequestMeta(
            source_type="upload:saved_search_csv",
            requested_at=datetime.now(UTC),
            request_detail={"size_bytes": len(raw_input)},
        )

        if not raw_input.strip():
            return IngestResult(
                request=request,
                rows=[],
                rows_understood=0,
                rows_skipped=0,
                columns_recognized=[],
                columns_ignored=[],
                skip_reasons=[],
                unavailable_reason="uploaded file was empty",
            )

        text = _decode(raw_input)

        try:
            dialect = csv.Sniffer().sniff(text[:4096])
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            return IngestResult(
                request=request,
                rows=[],
                rows_understood=0,
                rows_skipped=0,
                columns_recognized=[],
                columns_ignored=[],
                skip_reasons=[],
                unavailable_reason="no header row found in uploaded file",
            )

        header_map = {raw: _normalize_header(raw) for raw in reader.fieldnames}
        columns_recognized = sorted(
            {v for v in header_map.values() if v in _HEADER_ALIASES.values()}
        )
        columns_ignored = sorted(
            {v for v in header_map.values() if v not in _HEADER_ALIASES.values()}
        )

        rows: list[dict] = []
        skip_reasons: list[str] = []
        rows_skipped = 0

        for line_number, raw_row in enumerate(reader, start=2):
            if raw_row is None or all(not (v or "").strip() for v in raw_row.values()):
                continue  # blank row — noise, not a gap

            normalized_row = {header_map[k]: v for k, v in raw_row.items() if k in header_map}

            if not any(normalized_row.get(col) for col in _IDENTIFYING_COLUMNS):
                rows_skipped += 1
                skip_reasons.append(f"row {line_number}: no identifying column present, dropped")
                continue

            if "occurred_at" in normalized_row and normalized_row["occurred_at"]:
                parsed = _try_parse_date(normalized_row["occurred_at"])
                if parsed is not None:
                    normalized_row["occurred_at"] = parsed
                else:
                    skip_reasons.append(
                        f"row {line_number}: unparsed date '{normalized_row['occurred_at']}' "
                        "kept as raw text"
                    )

            rows.append(normalized_row)

        unavailable_reason = None
        if not rows:
            unavailable_reason = "no recognizable saved-search rows found"

        return IngestResult(
            request=request,
            rows=rows,
            rows_understood=len(rows),
            rows_skipped=rows_skipped,
            columns_recognized=columns_recognized,
            columns_ignored=columns_ignored,
            skip_reasons=skip_reasons,
            unavailable_reason=unavailable_reason,
        )
