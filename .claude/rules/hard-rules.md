## Hard Rules

- ALWAYS keep client NetSuite access read-only.
- ALWAYS preserve evidence provenance.
- ALWAYS validate external API and LLM responses.
- ALWAYS state which inputs were unavailable rather than hiding the gap.
- ALWAYS run lint/typecheck and relevant tests before finishing.
- NEVER invent NetSuite API behaviour — verify against docs.oracle.com or label it
  unverified.
- NEVER re-open settled decisions (OAuth 2.0, read-only, client-as-payer) without
  new evidence.
- NEVER commit secrets or client data.
- NEVER push directly to `main`.
- NEVER silently discard unavailable evidence.
- NEVER convert correlation into confirmed causation.
- Prefer small, surgical changes over rewrites.
- If 2–3 approaches fail, stop and reassess.
