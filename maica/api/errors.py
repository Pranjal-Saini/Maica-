from fastapi import Request, status
from fastapi.responses import JSONResponse

from maica.ingest.errors import IngestValidationError


async def ingest_validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IngestValidationError)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "ingest_validation_error", "message": str(exc)}},
    )
