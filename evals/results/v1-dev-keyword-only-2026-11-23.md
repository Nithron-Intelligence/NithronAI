# nai-bench v1-dev-keyword-only – 2026-11-23

NAI_EMBEDDINGS=off (keyword-only mode, BM25), reranker off, no LLM; nai-core built from lab/stage-0 with keyword-only mode; v1 corpus index of the granite97 run (stored vectors unused); Ryzen 9 7950X host

**PROVISIONAL — includes unreviewed items.** Review: 0 of 62 items human-reviewed (0 rejected); evaluated: 62 (all non-rejected items). Published numbers use `--reviewed-only`.

nAI 0.6.0 at commit `730e70e+dirty`; embeddings `ibm-granite/granite-embedding-97m-multilingual-r2` (None); reranker `off`; 47 answerable + 15 unanswerable questions over 100 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| auto | 0.842 | 0.808 | 0.894 | 0.809 | 0.204 | 0.787 | 0.800 |
| hybrid | 0.842 | 0.808 | 0.894 | 0.809 | 0.204 | 0.787 | 0.800 |
| bm25 | 0.842 | 0.808 | 0.894 | 0.809 | 0.204 | 0.787 | 0.800 |

Hit@5 / MRR by category (bm25):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 14 | 0.643 | 0.554 |
| lookup | 12 | 1.000 | 0.958 |
| multi-hop | 11 | 1.000 | 1.000 |
| table/scan-OCR | 10 | 1.000 | 0.933 |
| *same language* | 33 | 1.000 | 0.965 |
| *question language ≠ source language* | 14 | 0.643 | 0.554 |

Hit@5 / MRR by question language (bm25):

| Language | n | Hit@5 | MRR |
|---|---|---|---|
| de | 14 | 0.929 | 0.893 |
| en | 7 | 0.714 | 0.619 |
| fr | 10 | 1.000 | 1.000 |
| pt | 10 | 0.900 | 0.900 |
| sv | 6 | 0.833 | 0.625 |

Answerable questions with no result at all (embedding search drops hits below `NAI_EMBEDDINGS_MIN_SCORE`, cosine 0.3 by default):

| Method | same language: no result | question language ≠ source language: no result |
|---|---|---|
| auto | 0 of 33 | 0 of 14 |
| hybrid | 0 of 33 | 0 of 14 |
| bm25 | 0 of 33 | 0 of 14 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.532 | 0.575 | 0.894 | 0.000 | 0.000 | 0.000 | 0.919 | – | – | 0.011 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
