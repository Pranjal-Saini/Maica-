## Reasoning Rules

- The system performs **contributing-factor analysis**, not root-cause determination.
- Rank factors by strength of support and label each:
  - `CONFIRMED` — directly proven by evidence.
  - `LIKELY` — strongly supported but not proven.
  - `UNCERTAIN` — evidence exists, important gaps remain.
  - `INSUFFICIENT_EVIDENCE` — no reliable conclusion available.
- A component touching a field does not prove it caused the outcome. Never convert
  correlation into confirmed causation.
- Never treat a `SYSTEM` actor as proof of a manual action.
- Never blame a script, workflow, integration, or user without supporting evidence.
- Prefer chronological evidence and direct record relationships over inference.
- **Degrade gracefully on partial access.** Analyse what is readable and state
  plainly which inputs were missing. A diagnostic that names its blind spots is
  more trustworthy, not less.
- The LLM explains evidence; it is not the source of truth.
