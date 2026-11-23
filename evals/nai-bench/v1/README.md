# nai-bench v1 (in progress)

**Corpus: 100 files, questions: 100 (2026-11-23)**; targets ≥ 300 files and 625 questions. All items are
**unreviewed**: no v1 number is publishable until people review them (`review.py --file …`).

Questions: 4 per category per language (lookup, cross-lingual, table/scan-OCR, multi-hop, unanswerable ×
en/de/sv/fr/pt = 100; 80 answerable, 20 unanswerable, mostly near misses). Split by hash: **dev 43, test
57**; per-cell counts vary because the split is per item, not stratified (dev: lookup 6, cross-lingual 12,
table/OCR 6, multi-hop 9, unanswerable 10). Difficulty: 19 easy, 57 medium, 24 hard (target 30/40/30: later
batches need more easy and hard items). Every question was written by Claude (claude-opus-5-5) on 2026-11-23
(`provenance.written_by: "Claude-written"`, `use: eval-only`). Questions about EU acts list all five
language versions as gold sources (each one answers them), so EU acts are not used for cross-lingual items.
Law facts used in answers were checked against the stored texts; each gold fact matches its gold answer.

| Group | Files | License |
|---|---|---|
| Fictional household/studio documents (incl. 10 scans and photos) | 45 | CC-BY-4.0, Claude-written, eval-only |
| EU acts in en/de/sv/fr/pt | 20 | © European Union, reuse with attribution |
| German and Swedish statutes, US federal rules (16 CFR) | 20 | public domain (official texts) |
| Public-domain books (distractors) | 15 | public domain |

Languages: en 30, de 21, sv 18, fr 16, pt 15. Formats: text 37, PDF 27, HTML 23, scanned PDF 5, photo
(PNG) 5, DOCX 3. All 10 scans were checked with nAI's own OCR (Tesseract `eng+deu` in the nai-core image):
every key number and id is read correctly.

v1 is the first nai-bench version meant to back model claims ([V1_PLAN.md](../V1_PLAN.md)). v0 in the
parent folder stays frozen as the smoke set.

| Path | What |
|---|---|
| `corpus/` | The files nAI indexes (index this folder). |
| `corpus-manifest.json` | Every corpus file: language, kind, license, source, source URL, author, retrieval date, SHA-256. |
| `corpus-src/*.src.md` | Fictional documents written for nai-bench (front matter: output path, format, language, author, `use: eval-only`), rendered by `../build_corpus.py --root evals/nai-bench/v1`. |
| `sources.json` | The third-party downloads (URL, headers, license, author) that `fetch_corpus.py` fetches. |
| `fetch_corpus.py` | Downloads `sources.json` with curl into `corpus/` and updates the manifest; `--check` verifies the corpus. |
| `questions-dev.jsonl`, `questions-test.jsonl` | The questions, split by hash of the id ([split rules](../README.md#devtest-split-v1)). The test file is only read in final runs. |

```bash
apps/nai-core/.venv/bin/python evals/nai-bench/v1/fetch_corpus.py --check   # verify (also a test)
apps/nai-core/.venv/bin/python evals/nai-bench/v1/fetch_corpus.py           # fetch missing sources
# render the fictional files (build deps: evals/nai-bench/requirements-build.txt, e.g. in their own venv)
python evals/nai-bench/build_corpus.py --root evals/nai-bench/v1             # byte-reproducible
```

## Fictional documents

Same household as v0 (Jonas and Elin Berg, Freiburg; the summer cabin Björkudden in Dalarna; Elin's design
studio Nordlicht Studio), now with the studio's freelancer in Lyon and clients in Annecy, Porto and Portland
(OR). Several files point at the official texts (a heating-cost statement and the HeizkostenV, a washer-dryer
defect and the sale-of-goods directive, a delayed US order and the FTC mail-order rule), which the multi-hop
questions use. Every person, company, address, phone number (555), account number (00 check digits) and
e-mail domain (`.example`) is invented. All fictional files were written by Claude (claude-opus-5-5) on
2026-11-23, are CC-BY-4.0 and `use: eval-only`.

## Sources and licenses

Only openly reusable material; no personal data, no CC-BY-SA or non-commercial material.

| Corpus folder | Source | License |
|---|---|---|
| `Recht/EU/` | EU acts as published in the Official Journal, fetched from the EU Publications Office (CELLAR, same texts as EUR-Lex) in en/de/sv/fr/pt | Reuse authorised with attribution: **© European Union, https://eur-lex.europa.eu** (Commission Decision 2011/833/EU, EUR-Lex legal notice). Only the Official Journal version is authentic. |
| `Recht/Deutschland/` | Federal regulations from gesetze-im-internet.de | Public domain as official works (§ 5 Abs. 1 UrhG) |
| `Juridik/Sverige/` | Swedish statutes from data.riksdagen.se | Not protected (9 § upphovsrättslagen) |
| `Docs/US/CFR/` | FTC and CPSC consumer rules, 16 CFR (2024 edition), PDFs from govinfo.gov | Public domain, work of the US Government (17 U.S.C. § 105); regulatory text only |
| `Buecher/<lang>/` | Distractors: novels and stories in their original language from Project Gutenberg (pglaf.org mirror), authors who died before 1956 | Public domain in the US and the EU; Gutenberg header/licence removed |

Files are stored byte-exact as downloaded (the manifest's `sha256`). Project Gutenberg books are the one
exception: their Gutenberg header and licence are removed (`"transform": "gutenberg-strip"`; the
download's hash is kept as `download_sha256`). Every v1 item, including these files, is `use: eval-only`:
nothing from nai-bench is ever used for training.

Retrieved 2026-11-23. EUR-Lex itself answers curl with a JavaScript challenge, which is why the EU texts
come from the Publications Office's content API (`http://publications.europa.eu/resource/celex/<CELEX>`
with `Accept-Language`); gutenberg.org answers 503 and consumer.ftc.gov 403, hence the pglaf.org mirror and
the CFR texts on govinfo.gov. US federal consumer *guides* (V1_PLAN.md) are still to come from a source that
allows curl.
