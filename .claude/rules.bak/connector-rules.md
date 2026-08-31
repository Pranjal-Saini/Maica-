## NetSuite Connector Rules

- Keep connector operations read-only.
- Support REST and SuiteQL through separate adapters where practical.
- Preserve the original NetSuite response for auditability.
- Handle permissions, unavailable records, API failures, rate limits, and partial responses explicitly.
- Never assume that every NetSuite account exposes the same evidence.
- Record what data was requested, what was returned, and what was unavailable.
- Design the connector so additional NetSuite data sources can be added without changing the reasoning layer.
