## Security

- Read-only access, always. "We cannot modify anything in your account" is the
  strongest sentence available in a client security conversation — keep it true.
- Least-privilege NetSuite access; request no scope the analysis does not use.
- Keep client secrets and refresh tokens in environment-managed secret storage.
- Never log tokens, secrets, or full client records.
- Never expose NetSuite credentials or tokens to the frontend.
- Enforce tenant isolation on every client-specific operation.
- Validate authorization before serving any evidence.
- Encrypt sensitive data at rest and in transit.
- Treat uploaded logs and exports as untrusted input.
