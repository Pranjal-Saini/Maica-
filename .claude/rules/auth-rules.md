## Auth & Connection Rules

- **OAuth 2.0 authorization code flow. Settled — do not re-litigate.** Not TBA
  (OAuth 1.0a), which was the original plan and has been dropped.
- Browser consent means we never hold client credentials. Never build a flow that
  asks a user to paste a NetSuite password or token into this application.
- The integration record can be created by an administrator *or* by a holder of the
  Integration Application permission. Client ID and secret are displayed **once
  only** at creation — the setup flow must tell the user to capture them then.
- Store refresh tokens in environment-managed secret storage, never in the database
  in plaintext and never in the frontend.
- Handle token expiry and re-consent as normal states, not as errors.
