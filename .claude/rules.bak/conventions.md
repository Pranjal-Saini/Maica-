## Conventions

- Use typed interfaces between system layers.
- Use explicit identifiers such as `transaction_id`, `script_id`, `workflow_id`, and `integration_id`.
- Keep business logic out of API route handlers.
- Keep external API calls isolated behind service interfaces.
- Use structured logging with request and tenant identifiers.
- Return consistent API errors.
- Validate all external input.
- Keep LLM prompts and response schemas versioned.
- Prefer small modules with one clear responsibility.
