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

Static UI contracts are grouped into labeled `subTest` cases through
`tests.support.ContractTestCase`. This keeps the reported test count useful
without losing the specific contract name when an assertion fails. Security,
data-integrity, retrieval, and recovery behaviors remain independent tests so
one failure cannot hide another.

Tests must not contact live external APIs or write into production runtime
state. Use temporary directories, fake provider responses, and in-memory test
doubles. Generated `__pycache__`, `.pytest_cache`, coverage, and test-result
artifacts are ignored and should not be committed.
