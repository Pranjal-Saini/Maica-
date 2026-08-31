## LLM Rules

- Send only the evidence relevant to the question being asked.
- Never send secrets or unnecessary client data.
- Require structured JSON responses; validate every response against its schema.
- Reject or repair malformed output before it reaches the application.
- The model may not invent evidence. Every factor it returns must cite stored records.
- Preserve the evidence used to generate each finding.
- Do not trade evidence quality for model speed or cost.
- Keep prompts and response schemas versioned.
