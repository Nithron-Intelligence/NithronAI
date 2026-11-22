# nai-bench

A public benchmark of **NAS-style questions** over a small, realistic, multilingual file tree:
contracts, invoices, scanned letters, photographed receipts, manuals, meeting notes, spreadsheets, code
and statute excerpts in German, English, Swedish, French and Portuguese. It measures what nAI has to get
right: finding the right file (and page) for a question, answering from it with a citation, and saying
so when the files don't contain the answer.

**Version: v0 (2026-11-22)**: 27 files, 56 questions. Baseline:
[`../results/baseline-2026-11-22.md`](../results/baseline-2026-11-22.md).

## Goals

1. **Measure nAI end to end** on the kind of data people keep on a NAS, through its real API
   (`/search`, `/ask/stream`), including OCR, chunking and streaming.
2. **Back every model claim** of the Nithron AI lab with a number (lab principle 4).
3. **Stay small, private-by-design and legally clean**: fictional documents written for the benchmark
   plus public-domain texts; no personal data, no scraped documents.
4. **Never become training data** (lab principle 3 and the no-contamination rule).

Non-goals for v0: a leaderboard-grade number. At 56 questions a single question moves a rate by about
2 points; treat differences under ~0.05 as noise. v1 adds a test split, more files and human review.

## Layout

| Path | What |
|---|---|
| `corpus/` | The files nAI indexes, as they would sit on a NAS. Index this folder. |
| `corpus-src/*.src.md` | One source text per corpus file, with front matter (output path, format, language, license, provenance). |
| `build_corpus.py` | Renders `corpus-src/` into `corpus/` (text PDFs, scanned image PDFs, receipt photos, DOCX, plain files) and writes `corpus-manifest.json`. Byte-reproducible. |
| `corpus-manifest.json` | Every corpus file with language, kind, page count, license, source, provenance and SHA-256. |
| `questions.jsonl` | The questions, one JSON object per line. |

Rebuild after editing a source text (build-only dependencies: reportlab, python-docx, Pillow, a TTF font
with Latin-1 glyphs such as Noto Sans or DejaVu Sans):

```bash
pip install -r evals/nai-bench/requirements-build.txt
python evals/nai-bench/build_corpus.py          # rebuild corpus/ and the manifest
python evals/nai-bench/build_corpus.py --check  # verify files against the manifest (also a test)
```

## Question schema

```json
{
  "id": "nb-038",
  "question": "Ist die Kaution in meinem Mietvertrag gesetzlich zulässig?",
  "language": "de",
  "gold_answer": "Ja. Die Kaution beträgt 3.450 €, also genau das Dreifache der Kaltmiete …",
  "gold_facts": ["zulässig|ja", "dreifache|drei monatsmieten|3 monatsmieten|1.150|1150|551"],
  "forbidden_facts": ["nicht zulässig", "unzulässig", "nicht erlaubt"],
  "gold_sources": [
    {"file": "Wohnung/Mietvertrag_Ahornweg7.pdf", "page": 2, "section": "§ 4 Mietsicherheit (Kaution)"},
    {"file": "Gesetze/BGB_Mietrecht_Auszug.txt", "page": null, "section": "§ 551"}
  ],
  "category": "multi-hop",
  "difficulty": "hard",
  "provenance": {"author": "claude", "model": "claude-opus-5-5", "created": "2026-11-22",
                 "method": "hand-written from the corpus source texts", "human_reviewed": false,
                 "use": "eval-only"},
  "notes": null
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable id `nb-NNN`; never reused. |
| `question` | string | As a user would type it. |
| `language` | `en` `de` `sv` `fr` `pt` | Language of the question; the answer should use it too. |
| `gold_answer` | string \| null | Reference answer; `null` for unanswerable items. |
| `gold_facts` | string[] | Short strings a correct answer must contain; `a\|b` means either. Matching ignores case and number formatting (`1.012,40` = `1,012.40`, `238,00` = `238`, `1 200` = `1200`) and needs token boundaries (`300` does not match `3000` or `300.50`; `30.11` does match `30.11.2024`). |
| `forbidden_facts` | string[] (optional) | Strings that make an answer wrong even if the gold facts are there, for yes/no questions (`nicht erlaubt`). |
| `gold_sources` | object[] | `file` (path inside `corpus/`), `page` (1-based for PDFs, else `null`), `section` (heading, informative). |
| `category` | see below | |
| `difficulty` | `easy` `medium` `hard` | Author's estimate. |
| `provenance` | object | Who wrote the item and how; `use` must be `eval-only` for anything written by an AI service (lab principle 3). |
| `notes` | string \| null | Why an unanswerable item is unanswerable (often a near miss). |

`evals/naibench.py::validate` enforces the schema (also in CI): unique ids, known categories and
languages, gold files that exist in the manifest, pages that exist, cross-lingual items whose sources are
in another language, unanswerable items without gold, and at least 10 unanswerable items.

## Categories (v0 counts)

| Category | n | What it tests |
|---|---|---|
| `lookup` | 16 | One fact from one file, question in the file's language. |
| `cross-lingual` | 10 | Question in a different language than the file (EN→DE, DE→SV, SV→EN, PT→DE, …). |
| `table/scan-OCR` | 10 | The fact is in a table (text PDF, CSV) **or** in an image-only scan/photo that needs OCR. |
| `multi-hop` | 9 | Needs two files (or two places) and sometimes a small computation (date difference, premium increase, deposit vs. legal limit). |
| `unanswerable` | 11 | The files don't contain the answer; most are near misses (the topic is there, the fact isn't). The right answer is a refusal. |

Question languages: 25 English, 19 German, 7 Swedish, 3 Portuguese, 2 French.

Each item has one category, but 14 questions are cross-lingual in fact (the question's language differs
from every gold source's language; several multi-hop and table items are too). Results are therefore also
reported by this derived flag (`by_cross_lingual`), next to the category breakdown.

## Scoring

Retrieval ([`../retrieval/`](../retrieval/README.md)), answerable questions only, document level:
Recall@K, Precision@K (relevant files in the top K divided by K), Hit@K, MRR, nDCG@K, and Page Hit@K
(right file **and** right page).

Answers ([`../answers/eval_answers.py`](../answers/eval_answers.py)), through `/ask/stream`. The
`**Sources:**` list nAI appends is removed before scoring the text.

| Metric | Applies to | Definition |
|---|---|---|
| `correct` | answerable | every gold fact is in the answer and no forbidden fact is |
| `fact_recall` | answerable | share of gold facts in the answer |
| `citation_hit` | answerable | a gold file is among the citations nAI returned |
| `inline_citation_precision` | answerable | of the corpus file names the answer text mentions, the share that are gold (`null` if it names none) |
| `unsupported_numbers` | answerable | numbers (≥ 2 digits) in the answer that appear in no cited passage, the question or a cited path; reported as the share of answers with any (a cheap hallucination signal). Correctly computed numbers (nb-037's 16 days, nb-043's 40.60) also count, so read it per question. |
| `false_refusal` | answerable | the answer says the files don't contain it (and is missing a gold fact) |
| `correct_refusal` | unanswerable | the answer says the files don't contain it |
| `language_match` | all | a small stopword detector finds the question's language in the answer (`null` if unsure) |

Refusals are detected with multilingual phrase patterns (`naibench.REFUSAL_PATTERNS`); they are
heuristics and are tested, but an answer that refuses in unusual words can be missed. For extractive mode
(no LLM) the refusal and language numbers say little, since the answer is quoted text.

### Optional LLM judge

`--judge-url` / `--judge-model` (any OpenAI-compatible endpoint, e.g. Ollama) adds a judge. It sees the
question, the reference answer (or `UNANSWERABLE`), the retrieved passages and the answer, at temperature
0, with exactly this rubric (`eval_answers.JUDGE_RUBRIC`):

```text
You grade one answer from a question-answering system over a user's private files.
You get the question, the reference answer (or "UNANSWERABLE" if the files do not contain the answer),
the passages the system retrieved, and the system's answer.

Score each criterion and reply with JSON only:
{"correct": 0|1|2, "grounded": 0|1|2, "refusal_ok": true|false, "explanation": "<one sentence>"}

correct:    2 = agrees with the reference answer on every fact that matters;
            1 = partly right or missing a key fact; 0 = wrong, or answers an UNANSWERABLE question.
            For UNANSWERABLE questions: 2 if the answer says the files don't contain it, else 0.
grounded:   2 = every claim is supported by the retrieved passages; 1 = minor unsupported detail;
            0 = a key claim is not supported by the passages (even if it happens to be true).
refusal_ok: true if the answer refuses exactly when it should (refuses on UNANSWERABLE,
            answers otherwise); false if it refuses wrongly or invents an answer.
```

Judge scores are reported normalized to 0–1 (`judge_correct_norm`, `judge_grounded_norm`). The judge is
optional because it costs time and is itself a model with biases; the deterministic metrics are the
primary numbers. Record the judge model with the results (run_baseline does). Judge outputs are eval data
and are never used for training.

## Corpus

All people, companies, street addresses, phone numbers, account numbers and products in the fictional
documents are invented (`.example` domains, `555` phone numbers, `00` IBAN check digits). Some real brand names
(e.g. a car model, foods on a receipt) appear as everyday details. The two statute excerpts are real,
public-domain official texts.

The household behind the files: Jonas and Elin Berg in Freiburg (DE), with a summer cabin rented in
Dalarna (SE), and Elin's two-person design studio "Nordlicht Studio". Files reference each other the way
real files do (the meeting notes mention the hosting invoice; the travel plan mentions the cabin
contract), which is what the multi-hop questions use. Near-duplicate files (2023 vs. 2024 car insurance,
2023 vs. 2024 hosting invoice) test whether retrieval picks the right year.

| File | Lang | Kind | Format | License | Source |
|---|---|---|---|---|---|
| `Arbeit/Nordlicht/Angebote/Proposta_Pastelaria_Sol.md` | pt | proposal | text | CC0-1.0 | written for nai-bench (fictional) |
| `Arbeit/Nordlicht/Finanzen/budget_2024_Q1.csv` | en | spreadsheet | text | CC0-1.0 | written for nai-bench (fictional) |
| `Arbeit/Nordlicht/Meetings/2024-03-12_Kickoff_Kornfeld.md` | de | meeting notes | text | CC0-1.0 | written for nai-bench (fictional) |
| `Arbeit/Nordlicht/Meetings/2024-04-02_weekly_sync.md` | en | meeting notes | text | CC0-1.0 | written for nai-bench (fictional) |
| `Arbeit/Nordlicht/Rechnungen/invoice_2023-089_cloudberry.pdf` | en | invoice | pdf | CC0-1.0 | written for nai-bench (fictional) |
| `Arbeit/Nordlicht/Rechnungen/invoice_2024-117_cloudberry.pdf` | en | invoice | pdf | CC0-1.0 | written for nai-bench (fictional) |
| `Gesetze/BGB_Mietrecht_Auszug.txt` | de | statute | text | public domain (§ 5 Abs. 1 UrhG) | [BGB §§ 535, 551, 573c, gesetze-im-internet.de](https://www.gesetze-im-internet.de/bgb/), 2026-11-22 |
| `Gesetze/Jordabalken_12kap_utdrag.txt` | sv | statute | text | public domain (9 § URL) | [Jordabalk 12 kap. 4 §, data.riksdagen.se](https://data.riksdagen.se/dokument/sfs-1970-994.text), 2026-11-22 |
| `Handbuecher/Aurora_SilentWash_SW600_manual_EN.pdf` | en | manual | pdf, 3 pages | CC0-1.0 | written for nai-bench (fictional) |
| `Handbuecher/NetHaven_AX3000_quickstart.md` | en | manual | text | CC0-1.0 | written for nai-bench (fictional) |
| `Handbuecher/ThermaComfort_TC20_Bedienungsanleitung.pdf` | de | manual | pdf, 2 pages | CC0-1.0 | written for nai-bench (fictional) |
| `Handbuecher/notice_poele_granules_Flamea_P8.md` | fr | manual | text | CC0-1.0 | written for nai-bench (fictional) |
| `Rechnungen/IMG_2231.png` | de | receipt | photo (OCR) | CC0-1.0 | written for nai-bench (fictional) |
| `Rechnungen/scan_0042.pdf` | de | invoice | scanned PDF (OCR) | CC0-1.0 | written for nai-bench (fictional) |
| `Reisen/Reiseplan_Schweden_Sommer2024.md` | de | notes | text | CC0-1.0 | written for nai-bench (fictional) |
| `Sverige/faktura_stuga_2024.pdf` | sv | invoice | pdf | CC0-1.0 | written for nai-bench (fictional) |
| `Sverige/hyresavtal_stuga_Bjorkudden.docx` | sv | contract | docx | CC0-1.0 | written for nai-bench (fictional) |
| `Sverige/kvitto_Dalabutiken_Leksand.png` | sv | receipt | photo (OCR) | CC0-1.0 | written for nai-bench (fictional) |
| `Sverige/protokoll_vagsamfallighet_2024-05-18.docx` | sv | meeting notes | docx | CC0-1.0 | written for nai-bench (fictional) |
| `Technik/homelab/backup.sh` | en | code | text | CC0-1.0 | written for nai-bench |
| `Technik/homelab/docker-compose.yml` | en | code | text | CC0-1.0 | written for nai-bench |
| `Technik/photo_sorter.py` | en | code | text | CC0-1.0 | written for nai-bench |
| `Versicherungen/Hausrat_Police_2024.pdf` | de | contract | pdf | CC0-1.0 | written for nai-bench (fictional) |
| `Versicherungen/Kfz-Versicherung_2023.pdf` | de | contract | pdf | CC0-1.0 | written for nai-bench (fictional) |
| `Versicherungen/Kfz-Versicherung_2024.pdf` | de | contract | pdf, 2 pages | CC0-1.0 | written for nai-bench (fictional) |
| `Wohnung/Mietvertrag_Ahornweg7.pdf` | de | contract | pdf, 3 pages | CC0-1.0 | written for nai-bench (fictional) |
| `Wohnung/Nebenkostenabrechnung_2023.pdf` | de | statement | scanned PDF (OCR) | CC0-1.0 | written for nai-bench (fictional) |

`corpus-manifest.json` is the authoritative list (with hashes); `build_corpus.py --table` prints it.

## Licensing and provenance

- **License:** nai-bench (questions, source texts, rendered files, manifest) is released under
  **CC0-1.0**, except the two statute excerpts, which are public domain as official texts. The eval code in
  `evals/` is under the repository license (NCL).
- **Provenance:** the fictional documents and all 56 questions were written by Claude (claude-opus-5-5) on
  2026-11-22, from the source texts in this folder, and are marked `"author": "claude"`,
  `"use": "eval-only"`. Under the lab's principle 3 they must **never** be used as training data or to
  generate training data. `human_reviewed` is `false` for every v0 item.
- **No personal data:** no real person's data and no real company's documents are in the corpus.

## Known limitations of v0

- **Small.** 27 files and 45 answerable questions: retrieval is easier than on a real NAS with thousands
  of files, and confidence intervals are wide. v1 target: ≥ 300 files (most of them distractors), ≥ 300
  questions, a fixed dev/test split.
- **Single author, no human review yet.** Every item needs a second (human) reviewer before v1.
- **OCR languages.** The nAI image ships Tesseract `eng+deu`; the Swedish receipt is read with those
  models. That is realistic for today's nAI but mixes OCR quality into the retrieval score.
- **Synthetic documents are cleaner than real ones** (no handwriting, no skewed phone photos, no
  multi-column layouts). Scans are rendered with mild rotation, blur and noise only.
- **Heuristic answer metrics.** Fact matching, refusal and language detection are deterministic
  heuristics, so read the per-question output before trusting small differences.

## Adding questions

1. Add or edit source texts in `corpus-src/` (fictional or public-domain only; record license and
   provenance in the front matter) and rebuild the corpus.
2. Append items to `questions.jsonl` with the next free id and a truthful `provenance` (who wrote it,
   with which tool, `use: eval-only` if an AI service wrote it).
3. Run `pytest evals/tests` (schema and manifest checks) and a baseline.
4. Any change to questions or corpus changes the dataset hashes that `run_baseline.py` records, so results
   from before and after are not comparable. Bump the version in this README.
