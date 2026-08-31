## Hard Rules

- ALWAYS keep customer NetSuite access read-only.
- ALWAYS preserve evidence provenance.
- ALWAYS validate external API and LLM responses.
- ALWAYS test changes before finishing.
- ALWAYS run lint/typecheck and relevant tests before finishing.
- NEVER commit secrets or customer data.
- NEVER edit generated files manually.
- NEVER push directly to `main`.
- NEVER silently discard unavailable evidence.
- NEVER convert correlation into confirmed causation.
- Prefer small, surgical changes over large rewrites.
- If 2–3 approaches fail, stop and reassess before continuing.
