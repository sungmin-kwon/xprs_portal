# XPRS test suite

Run the complete offline suite from the repository root:

```bash
./.xprs_portal/bin/python -m unittest discover -s tests
```

The suite is organized around behavior rather than implementation layers:

- cohort access, privacy, pseudonymization, and repository safety;
- K-PREDICT data import, risk profiles, and rare-variant behavior;
- literature retrieval, provider caches, eligibility, ranking, and recovery;
- summary, report, plot, and task failure recovery;
- browser-facing navigation, copy, layout, and accessibility contracts.

`test_chatbot_quality.py` is the compact chatbot QC matrix. It protects four
high-risk behaviors with labeled subcases: request routing, multi-turn context
retention, consistency of displayed PRS/contribution numbers, and removal of
private K-PREDICT values before hosted-model calls. Add a regression case there
when a chatbot failure belongs to one of these boundaries.

The complementary golden set is stored in
`benchmarks/chatbot_quality_cases.json`. Validate its deterministic routing
cases without network calls using:

```bash
./.xprs_portal/bin/python scripts/evaluate_chatbot_quality.py
```

Add `--live --output /tmp/xprs-chatbot-quality/results.json` to run the
controlled, non-private generation cases through the configured model. The
generated Markdown report deliberately leaves scientific grounding items as
manual checkboxes: automated citation syntax checks cannot prove that a paper
actually supports a claim.

Static UI contracts are grouped into labeled `subTest` cases through
`tests.support.ContractTestCase`. This keeps the reported test count useful
without losing the specific contract name when an assertion fails. Security,
data-integrity, retrieval, and recovery behaviors remain independent tests so
one failure cannot hide another.

Tests must not contact live external APIs or write into production runtime
state. Use temporary directories, fake provider responses, and in-memory test
doubles. Generated `__pycache__`, `.pytest_cache`, coverage, and test-result
artifacts are ignored and should not be committed.
