class IngestValidationError(Exception):
    """Raised only when input is so broken that nothing whatsoever can be extracted
    from it — e.g. not decodable as text at all. Malformed rows within an otherwise
    readable file are never raised; they are reported via IngestResult.skip_reasons."""
