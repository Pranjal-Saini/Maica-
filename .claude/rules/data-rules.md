## Data Rules

- Store raw inputs (API responses, uploaded files) separately from normalized data.
- Preserve source IDs, timestamps, field names, old values, new values, actor, and
  source type on every record.
- Every ranked factor must be traceable to stored evidence.
- Represent missing data explicitly. Never silently substitute an assumption.
- Keep client data isolated by tenant on every operation.
- Client data may be processed with client approval — treat all of it as
  confidential regardless.
- Retain only what the analysis needs, and be able to say what is retained.
