## Security

- Always use least-privilege NetSuite access.
- Keep NetSuite credentials and secrets in environment-managed secret storage.
- Never log access tokens, passwords, or full customer records.
- Never expose NetSuite credentials to the frontend.
- Enforce tenant isolation on every customer-specific operation.
- Validate authorization before accessing evidence.
- Encrypt sensitive data at rest and in transit.
- Treat uploaded logs and files as untrusted input.
