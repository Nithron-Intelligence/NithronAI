# nai-bench v1 plan

> Status: plan, 2026-11-23. v0 (27 files, 56 questions) stays frozen as the smoke-sized set; v1 is the first
> version whose numbers can back a model claim (lab principle 4).

## Why v0 is not enough

With 45 answerable questions, the 95 % confidence interval of the hybrid baseline's MRR (0.793) is
**±0.09** (normal approximation; a 5000-sample bootstrap gives 0.705–0.880). LLM answer correctness
(0.578) is **±0.14**. Any real improvement from Vane 1 or Loupe 1 (plausibly +0.03 to +0.08 MRR) would be
lost in that noise.

## Sample size: the math

For a mean of per-question scores with standard deviation σ, the 95 % margin of error is

    E = 1.96 · σ / √n        →        n = (1.96 · σ / E)²

Measured on v0 (`evals/results/baseline-2026-11-22.json`, 45 answerable questions):

| Per-question score | σ |
|---|---|
| reciprocal rank, BM25 | 0.399 |
| reciprocal rank, embedding | 0.352 |
| reciprocal rank, hybrid | 0.308 |
| paired difference hybrid − embedding | 0.343 |
| paired difference hybrid − BM25 | 0.249 |
| answer correct (0/1), p = 0.578 | √(p(1−p)) = 0.494 |

Required answerable questions:

| Target margin E | σ = 0.31 (hybrid MRR today) | σ = 0.35 (embedding MRR / paired diff) | σ = 0.40 (harder v1, more distractors) |
|---|---|---|---|
| ±0.05 | 148 | 189 | 246 |
| **±0.03** | **411** | **523** | **683** |
| ±0.02 | 923 | 1177 | 1537 |

Answer correctness is a 0/1 score, so it needs more: ±0.05 needs 385 questions, ±0.03 needs 1068
(worst case p = 0.5).

**Target for v1: 500 answerable questions + 125 unanswerable (625 total).** That gives about ±0.03 on MRR
when comparing two models on the same questions (paired σ ≈ 0.34 → E = 1.96 · 0.34 / √500 = 0.030), and
±0.044 on answer correctness. v1 is harder than v0 (hundreds of distractor files), so per-question σ will
likely grow towards 0.40; if it does, the measured margin is reported as is, and v1.1 grows to ~700. Every
report states its margin: `run_baseline.py` should add a bootstrap interval per metric (to do).

Unanswerable items: 125 gives ±0.088 on the correct-refusal rate at p = 0.5. That is enough to rank
models; ±0.05 would need 385, which is a v2 goal.

## Even spread

Answerable questions: 4 categories × 5 question languages × 25 = **500**.

| | en | de | sv | fr | pt | Total |
|---|---|---|---|---|---|---|
| lookup | 25 | 25 | 25 | 25 | 25 | 125 |
| cross-lingual | 25 | 25 | 25 | 25 | 25 | 125 |
| table / scan-OCR | 25 | 25 | 25 | 25 | 25 | 125 |
| multi-hop | 25 | 25 | 25 | 25 | 25 | 125 |
| unanswerable (≥ 60 % near misses) | 25 | 25 | 25 | 25 | 25 | 125 |

- Cross-lingual cells pair each question language with every other document language at least 5 times
  (e.g. the 25 Swedish cross-lingual questions point at English, German, French and Portuguese documents).
- Difficulty target per cell: 30 % easy, 40 % medium, 30 % hard.
- Each file gets at most 6 questions, so no single document dominates.
- The derived cross-lingual flag (`by_cross_lingual`) is reported next to the categories, as in v0.

## Corpus: at least 300 files

Target mix (files):

| Share | Files | Kind | Source and license |
|---|---|---|---|
| 35 % | ~110 | Household and small-office documents: contracts, invoices, statements, manuals, letters, meeting notes, receipts, spreadsheets, config and code | Written for nai-bench (fictional); author recorded per file (Claude or an approved open-weight model), CC-BY-4.0, eval-only |
| 25 % | ~75 | Official texts in all five languages: EU regulations and directives (e.g. GDPR, consumer-rights and product-safety texts) in de/en/sv/fr/pt; German and Swedish statutes | EUR-Lex (reuse allowed with attribution under Commission Decision 2011/833/EU; check each document's notice); German statutes are public domain (§ 5 UrhG); Swedish statutes are not protected (9 § URL) |
| 15 % | ~45 | US federal government publications (consumer guides, appliance and safety guidance) | Public domain (17 U.S.C. § 105); check that each document is a federal work with no third-party content |
| 15 % | ~45 | Distractors: public-domain books and long texts in the five languages | Project Gutenberg texts that are public domain in the US and the EU (author died before 1956), with the Gutenberg header/licence removed |
| 10 % | ~30 | Scans and photos: rendered from the fictional documents above, plus public-domain scanned forms | As above |

Rules:
- No CC-BY-SA or non-commercial material (keeps nai-bench compatible with CC-BY-4.0 except for attribution-only
  sources, which keep their attribution in the manifest).
- No personal data: real documents are official texts or public-domain books only.
- Every file has a manifest entry: source URL, license, retrieval date, author, SHA-256.
- No file from nai-bench may appear in any training corpus (`training/embed/check_overlap.py`).
- Statute sections used in v0 (BGB §§ 535, 551, 573c; Jordabalken 12:4) stay; new sections are fine.

## Writing and review

1. Draft questions per cell, from the source texts (Claude-written items are allowed in an eval set and
   are marked `"author": "claude", "use": "eval-only"`; open-weight models may draft too).
2. **Human review is required** for every item before it counts (`evals/nai-bench/review.py`, see the
   README). An item is published only with `review_status` `accepted` or `fixed`.
3. Split before any model is tuned: **dev 40 % / test 60 %** by hash of the item id (`sha256(id)` mod 100
   < 40 → dev), not stratified: a per-item rule never moves an existing item when items are added, which a
   stratified, seeded split would. Cells of 25 items get roughly 10 dev / 15 test. Test answers are never
   used for tuning or prompt changes; published numbers come from the test split, reviewed items only. The
   rules and the guard are in the README ("Dev/test split").
4. Freeze v1: tag the dataset (`nai-bench-v1.0`) and record its hashes; later fixes go into v1.1 with a
   changelog.

## Effort estimate

- Corpus collection and rendering: ~3–4 days.
- 625 questions drafted: ~2 days with model help; human review at ~1.5 min per item ≈ 16 hours.
- Running the full baseline on v1: < 1 hour on the bench stack.
