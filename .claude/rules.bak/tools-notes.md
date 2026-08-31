## Tools & Notes

- NetSuite is an external dependency; connector behavior must be validated against official documentation and real account behavior.
- Do not assume a live NetSuite account, permission, record, or log is available.
- Design for partial evidence and account-specific availability.
- The production system must remain useful even when some evidence sources are unavailable.
- Primary product output: transaction impact, event timeline, strongest supported causal chain, evidence, uncertainty, and recommended next investigation step.
- The application is pre-launch until real NetSuite connectivity, security, and end-to-end behavior have been validated.
