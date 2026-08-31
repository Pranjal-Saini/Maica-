## Reasoning Rules

- The system performs transaction impact analysis, not automatic root-cause determination.
- The system must distinguish:
  - `CONFIRMED` — directly proven.
  - `LIKELY` — strongly supported but not proven.
  - `UNCERTAIN` — evidence exists but important gaps remain.
  - `INSUFFICIENT_EVIDENCE` — no reliable cause can be established.
- A component changing a field does not prove that it caused the overall problem.
- Never treat a `SYSTEM` actor as proof of a manual action.
- Never blame a script, workflow, integration, or user without supporting evidence.
- Prefer chronological evidence and direct relationships.
- The LLM explains evidence; it is not the source of truth.
- Validate LLM output before returning it to users.
