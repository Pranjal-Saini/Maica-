## Conventions

- **Prefer Python.** Solo founder, part-time, night shift — favour boring, readable
  code over clever architecture.
- Use typed interfaces between layers.
- Use explicit identifiers: `transaction_id`, `script_id`, `workflow_id`,
  `integration_id`, `tenant_id`.
- Keep business logic out of route handlers.
- Keep external calls behind service interfaces.
- Use structured logging with request and tenant identifiers.
- Return consistent API errors; validate all external input.
- Small modules, one clear responsibility each.
