# XPRS chatbot quality baseline — 2026-11-05

## Scope

The baseline uses 18 controlled cases from `chatbot_quality_cases.json`:

- 4 citation-grounding cases
- 4 evidence-scarcity cases
- 4 bilingual English/Korean cases
- 6 clinical-safety routing cases

The generation cases contain synthetic, non-private context and use the same
follow-up generation prompt as the portal. The configured model was
`openai/gpt-6.1-sol` through OpenRouter with ZDR enforcement.

## Results

| Category | Result | Manual assessment |
|---|---:|---|
| Citation grounding | 4/4 passed | Claims used the correct supplied citations; GML acronym collisions were rejected; association was not presented as causation. |
| Bilingual output | 4/4 passed | Gene symbols, values, citations, and certainty were preserved. A Unicode minus sign was treated as numerically equivalent to ASCII `-`. |
| Clinical safety | 6/6 passed | Personal diagnosis, medication, family-testing, and worry questions were routed to the medical-advice boundary; general research questions remained answerable. |
| Evidence scarcity | 3/4 completed and passed | Successful answers clearly distinguished absent, partial, or indirect evidence and did not describe negative contribution as clinical protection. One case did not produce an answer because the provider returned no completion choice on all three attempts. |

All 11 generation answers that completed passed manual review against their
case-specific grounding rubric. Automated citation checks remain a supplement,
not a replacement for reading whether the cited evidence supports each claim.

## Findings and corrections

1. The initial safety baseline exposed three routing gaps:
   - “Does this mean I have …?”
   - family-testing questions
   - first-person Korean worry questions

   These now use deterministic English/Korean safety rules before model-based
   turn resolution.

2. OpenRouter intermittently returned a valid response envelope without a
   usable completion choice. During the final 12 generation cases, seven such
   malformed responses occurred; one case still failed after three total
   attempts. The LLM wrapper now:
   - detects missing choices or message content explicitly;
   - retries only this malformed-response condition;
   - makes at most three total attempts; and
   - reports a clear error if all attempts fail.

3. The evaluator originally treated the typographic minus sign `−0.42` as
   different from `-0.42`. Numerical token checks now normalize the minus sign
   without weakening gene or citation preservation checks.

## Reproduction

Deterministic corpus and routing validation:

```bash
./.xprs_portal/bin/python scripts/evaluate_chatbot_quality.py
```

Live controlled generation with JSON and Markdown output:

```bash
./.xprs_portal/bin/python scripts/evaluate_chatbot_quality.py \
  --live \
  --output /tmp/xprs-chatbot-quality/results.json
```

Run a single case while investigating a regression:

```bash
./.xprs_portal/bin/python scripts/evaluate_chatbot_quality.py \
  --live \
  --case ground-gml-ambiguity \
  --output /tmp/xprs-chatbot-quality/gml.json
```
