## Tools & Notes

- NetSuite is an external dependency. Verify connector behaviour against official
  documentation (docs.oracle.com, SuiteAnswers) and real account behaviour — never
  against training knowledge alone. Use the `netsuite-domain-expert` agent for this.
- Do not assume a live NetSuite account, permission, record, or log is available.
- Design for partial evidence and account-specific availability; the product must
  stay useful when some sources are missing.
- **Status:** research phase is closed. Access, auth, permission and buyer questions
  are answered. Next step is the OAuth 2.0 connection script — authenticate, pull one
  real transaction, try to trace it.
- Pre-launch until real NetSuite connectivity, security, and end-to-end behaviour are
  validated.
- Keep responses short and plain. Long dense answers with many tables are
  overwhelming — lead with the key point and stop.
