## NetSuite Connector Rules

- Connector operations are **read-only, always**. Never write to a client ledger.
- **Never poll speculatively.** NetSuite meters API usage per account; throttling
  annoys the client's administrator — the exact person onboarding depends on. Pull
  on demand, cache aggressively.
- Respect governance limits and back off explicitly on rate-limit responses.
- Support REST and SuiteQL through separate adapters where practical.
- Preserve the original NetSuite response for auditability.
- Handle permission denials, missing records, API failures, and partial responses
  as first-class outcomes, not exceptions to swallow.
- Never assume every NetSuite account exposes the same evidence.
- Record what was requested, what was returned, and what was unavailable.
- New data sources must be addable without changing the reasoning layer.
