# Security policy

## Secrets

Never commit `.env`, API keys, admin or evaluation tokens, evaluation responses,
session logs, Semantic Scholar response caches, Chroma databases, generated
benchmark corpora, private cohort RDS files, or rare-variant handoffs. Use
`.env.example` only as a key-free configuration template and run
`python scripts/check_public_repo.py` before publishing.

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
- Do not mount private K-PREDICT data into a public deployment.
- Terminate TLS at a trusted reverse proxy and restrict direct access to the
  application port.

## Private cohort deployments

- Enforce authorization on the API, not only in the browser interface.
- Keep private inputs and derivatives outside the repository and public static
  directories.
- Use pseudonymous browser-facing identifiers and avoid identifiers in URLs,
  filenames, routine logs, and error messages.
- Do not send individual IDs, genotypes, variants, HGVS values, or individual
  contribution vectors to Semantic Scholar or external language-model APIs.
- K-PREDICT OpenRouter calls must keep Zero Data Retention required and provider
  data collection denied. Do not weaken the prompt-minimization boundary to add
  raw/percentile PRS, exact contribution scores, demographics, or rare findings.
- K-PREDICT session logs must remain ephemeral until access, encryption,
  retention, and deletion policies have been approved. Generated reports remain
  authenticated downloads and are not retained server-side.
- Keep the public 1000 Genomes deployment and private K-PREDICT deployment on
  separate data roots and credentials.

## Reporting a vulnerability

Do not include secrets, private cohort data, or personal information in a
public issue. Use GitHub private vulnerability reporting after the repository
is published, or contact the repository owner privately.
