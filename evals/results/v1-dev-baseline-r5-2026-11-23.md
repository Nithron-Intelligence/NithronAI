# nai-bench v1-dev-baseline-r5 – 2026-11-23

nai-bench v1 **dev split** (62 items), PROVISIONAL: no v1 item is human-reviewed. Defaults (reranker off, answering LLM qwen2.5:1.5b); the reference for the round-5 reranker and phi4-mini runs (same 62 items). Stack: infra/compose.bench.yaml with nai-core 0.6.0 (local build of 06c29e0 = the published v0.6.0) indexing evals/nai-bench/v1/corpus (100 files), Ollama 0.40.17-rocm on an AMD Radeon RX 7900 XTX (24 GB); judge qwen2.5:7b; LLM temperature 0.

**PROVISIONAL — includes unreviewed items.** Review: 0 of 62 items human-reviewed (0 rejected); evaluated: 62 (all non-rejected items). Published numbers use `--reviewed-only`.

nAI 0.6.0 at commit `0c941ad`; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed); reranker `off`; 47 answerable + 15 unanswerable questions over 100 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| bm25 | 0.842 | 0.808 | 0.894 | 0.809 | 0.204 | 0.787 | 0.800 |
| embedding | 0.494 | 0.447 | 0.575 | 0.538 | 0.136 | 0.492 | 0.520 |
| hybrid | 0.720 | 0.596 | 0.894 | 0.829 | 0.217 | 0.724 | 0.840 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 14 | 0.714 | 0.582 |
| lookup | 12 | 1.000 | 1.000 |
| multi-hop | 11 | 1.000 | 0.697 |
| table/scan-OCR | 10 | 0.900 | 0.603 |
| *same language* | 33 | 0.970 | 0.779 |
| *question language ≠ source language* | 14 | 0.714 | 0.582 |

Hit@5 / MRR by question language (hybrid):

| Language | n | Hit@5 | MRR |
|---|---|---|---|
| de | 14 | 0.929 | 0.714 |
| en | 7 | 0.571 | 0.596 |
| fr | 10 | 1.000 | 0.817 |
| pt | 10 | 0.900 | 0.800 |
| sv | 6 | 1.000 | 0.583 |

Answerable questions with no result at all (embedding search drops hits below `NAI_EMBEDDINGS_MIN_SCORE`, cosine 0.3 by default):

| Method | same language: no result | question language ≠ source language: no result |
|---|---|---|
| bm25 | 0 of 33 | 0 of 14 |
| embedding | 0 of 33 | 0 of 14 |
| hybrid | 0 of 33 | 0 of 14 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.489 | 0.511 | 0.872 | 0.000 | 0.000 | 0.000 | 0.806 | – | – | 0.044 |
| llm: ollama/qwen2.5:1.5b | 0.489 | 0.511 | 0.872 | 0.043 | 0.085 | 0.267 | 0.627 | 0.629 | 0.758 | 0.301 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
