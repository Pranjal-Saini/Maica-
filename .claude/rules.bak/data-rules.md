## Data Rules

- Store raw NetSuite responses separately from normalized data.
- Preserve source IDs, timestamps, field names, old values, new values, and source type.
- Every derived finding must be traceable to stored evidence.
- Represent missing data explicitly; never silently replace it with assumptions.
- Keep customer/account data isolated by tenant.
- Treat all customer NetSuite data as confidential.
