# Korean PDF fonts

The XPRS PDF renderer bundles regular and bold subsets of **Noto Sans KR** so
Korean reports render consistently without depending on fonts installed on the
deployment host.

- Upstream: <https://github.com/google/fonts/tree/main/ofl/notosanskr>
- Source file: `NotoSansKR[wght].ttf`
- License: SIL Open Font License 1.1 (`OFL-NotoSansKR.txt`)
- Static instances: weight 400 and weight 700
- Retained characters: Hangul syllables and jamo, Latin, Greek, punctuation,
  common mathematical symbols, arrows, currency symbols, and full-width forms

The subsets were generated from the upstream variable font with FontTools. The
font is embedded into generated PDFs by ReportLab.
