from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class IngestRequestMeta(BaseModel):
    """What was asked for. Shape of request_detail differs per source, but every
    source reports one of these — reasoning code never needs to know which."""

    source_type: str
    requested_at: datetime
    request_detail: dict


class IngestResult(BaseModel):
    """What one ingest call produced. Identical shape regardless of source, so
    downstream code (repository, normalizer, graph, reasoning) never branches on
    whether evidence came from an upload or a live NetSuite pull."""

    request: IngestRequestMeta
    rows: list[dict]
    rows_understood: int
    rows_skipped: int
    columns_recognized: list[str]
    columns_ignored: list[str]
    skip_reasons: list[str]
    unavailable_reason: str | None = None


class IngestSource(ABC):
    """One interface both upload parsers and the future NetSuite connector
    implement. Reasoning/graph code only ever imports this type, never a concrete
    subclass."""

    @abstractmethod
    def ingest(self, raw_input: bytes) -> IngestResult:
        """Parse untrusted raw bytes into an IngestResult.

        Must never raise on malformed input — malformed rows go into
        skip_reasons, not exceptions. Only raises IngestValidationError when
        the input is so broken nothing can be extracted at all.
        """
        raise NotImplementedError
