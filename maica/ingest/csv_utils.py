import csv
import io
import re
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
