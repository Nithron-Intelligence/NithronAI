# nai-bench v1-dev-baseline – 2026-11-23

nai-bench v1 **dev split** (43 items), PROVISIONAL: no v1 item is human-reviewed yet. Stack: infra/compose.bench.yaml with nai-core 0.6.0 (local build of main 06c29e0) indexing evals/nai-bench/v1/corpus (100 files) in its own data volume, Ollama 0.40.17-rocm on an AMD Radeon RX 7900 XTX (24 GB); defaults as in the 0.5.0 baseline: reranker off, answering LLM qwen2.5:1.5b at temperature 0, judge qwen2.5:7b.

**PROVISIONAL — includes unreviewed items.** Review: 0 of 43 items human-reviewed (0 rejected); evaluated: 43 (all non-rejected items). Published numbers use `--reviewed-only`.

nAI 0.6.0 at commit `22336af`; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed); reranker `off`; 33 answerable + 10 unanswerable questions over 100 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| bm25 | 0.841 | 0.818 | 0.879 | 0.774 | 0.206 | 0.765 | 0.812 |
| embedding | 0.557 | 0.515 | 0.606 | 0.570 | 0.151 | 0.545 | 0.625 |
| hybrid | 0.714 | 0.576 | 0.909 | 0.832 | 0.230 | 0.723 | 0.875 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 12 | 0.750 | 0.596 |
| lookup | 6 | 1.000 | 1.000 |
| multi-hop | 9 | 1.000 | 0.630 |
| table/scan-OCR | 6 | 1.000 | 0.792 |
| *same language* | 21 | 1.000 | 0.782 |
| *question language ≠ source language* | 12 | 0.750 | 0.596 |

Hit@5 / MRR by question language (hybrid):

| Language | n | Hit@5 | MRR |
|---|---|---|---|
| de | 9 | 1.000 | 0.741 |
| en | 5 | 0.600 | 0.613 |
| fr | 7 | 1.000 | 0.833 |
| pt | 7 | 0.857 | 0.786 |
| sv | 5 | 1.000 | 0.500 |

Answerable questions with no result at all (embedding search drops hits below `NAI_EMBEDDINGS_MIN_SCORE`, cosine 0.3 by default):

| Method | same language: no result | question language ≠ source language: no result |
|---|---|---|
| bm25 | 0 of 21 | 0 of 12 |
| embedding | 0 of 21 | 0 of 12 |
| hybrid | 0 of 21 | 0 of 12 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.515 | 0.515 | 0.909 | 0.000 | 0.000 | 0.000 | 0.791 | – | – | 0.058 |
| llm: ollama/qwen2.5:1.5b | 0.455 | 0.470 | 0.909 | 0.000 | 0.091 | 0.300 | 0.610 | 0.628 | 0.744 | 0.298 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.

## Reading the numbers (hand-written, 2026-11-23)

**PROVISIONAL.** First v1 run: dev split only (43 items: 33 answerable, 10 unanswerable), no item human-reviewed,
one run. With 33 answerable questions the 95 % margin on MRR is about ±0.1 (V1_PLAN.md), so treat this as a
first look, not a result. Nothing was tuned.

Cross-lingual retrieval (questions whose language differs from every gold source's language, n = 12):

| Method | same language Hit@5 / MRR (n = 21) | cross-language Hit@5 / MRR (n = 12) | cross-language misses at 5 |
|---|---|---|---|
| bm25 | 1.000 / 1.000 | 0.667 / 0.562 | v1-0026, v1-0028, v1-0045, v1-0087 |
| embedding | 0.571 / 0.525 | 0.667 / 0.613 | v1-0007, v1-0026, v1-0028, v1-0087 |
| hybrid | 1.000 / 0.782 | 0.750 / 0.596 | v1-0026, v1-0028, v1-0087 |

- **The 0.3 cosine cutoff emptied no result list on v1** (the table above: 0 of 33). The miss seen in the
  TrueNAS app test (one short note, nothing else indexed) doesn't happen with a 10 452-chunk corpus: some chunk
  always clears 0.3. On v1 the failure is **ranking**: for two of the embedding misses the top hit is a
  public-domain book (v1-0026 → *Effi Briest*, v1-0087 → *Die Verwandlung*), i.e. long distractor text in the
  question's language outranks the right document in another language.
- **Embedding search is weak even within one language** (Hit@5 0.571) while BM25 is perfect there: the
  multilingual MiniLM model ranks distractor chunks (books, long EU acts) above short household documents.
  Hybrid keeps BM25's same-language strength and gains a little on cross-language questions.
- This is the gap Vane 1 targets (Stage 1): cross-language Hit@5 / MRR and the embedding-only same-language
  numbers are the ones to beat, on the dev split for development and on the reviewed test split for the claim.
- Answers: qwen2.5:1.5b gets 0.455 of the answerable questions fully right (extractive 0.515) and refuses
  correctly on 3 of 10 unanswerable ones; judge (qwen2.5:7b) correct 0.628, grounded 0.744.
