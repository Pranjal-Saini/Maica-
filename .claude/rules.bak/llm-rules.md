## LLM Rules

- Send only relevant evidence to the model.
- Never send secrets or unnecessary customer data.
- Require structured JSON responses.
- Validate every model response against its schema.
- Reject or repair malformed output before returning it to the application.
- Do not let the model invent missing evidence.
- Preserve the evidence used to generate each finding.
- Do not optimize model speed at the cost of evidence quality.
