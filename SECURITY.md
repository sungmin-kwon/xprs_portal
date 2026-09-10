# Security policy

## Secrets

Never commit `.env`, API keys, admin or evaluation tokens, evaluation responses,
session logs, Semantic Scholar response caches, Chroma databases, or generated benchmark corpora. Use
`.env.example` only as a key-free configuration template.

If a secret is exposed, revoke it at the provider before removing it from Git
history. Removing a key from the latest commit does not invalidate copies in
earlier commits or forks.

## Public deployment

- Leave `SESSION_LOGGING_ENABLED=false` unless persistent logs are explicitly
  required and appropriately protected.
- Set a strong `XPRS_ADMIN_TOKEN`; the administration route is disabled when
  the token is absent.
- Leave `XPRS_EVALUATION_TOKEN` empty when the internal evaluation is not in
  progress. Keep `evaluation_responses/` private and define a retention and
  deletion policy before collecting participant responses.
- Protect OpenRouter-backed generation endpoints with authentication, edge
  access controls, rate limits, and provider-side spending limits.
- Do not mount private KFDA data into a public deployment.
- Terminate TLS at a trusted reverse proxy and restrict direct access to the
  application port.

## Reporting a vulnerability

Do not include secrets, private cohort data, or personal information in a
public issue. Use GitHub private vulnerability reporting after the repository
is published, or contact the repository owner privately.
