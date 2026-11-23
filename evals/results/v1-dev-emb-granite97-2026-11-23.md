# nai-bench v1-dev-emb-granite97 – 2026-11-23

nai-bench v1 **dev split** (62 items), PROVISIONAL: no v1 item is reviewed. Embedding model **ibm-granite/granite-embedding-97m-multilingual-r2** (fastembed; Granite R2 via nAI's custom ONNX registration, CLS pooling, no prefix), reranker off, no LLM (retrieval + extractive only). nai-core built from lab/stage-0 with the Granite registration; v1 corpus in its own index per model; RX 7900 XTX host (CPU embeddings).

**PROVISIONAL — includes unreviewed items.** Review: 0 of 62 items human-reviewed (0 rejected); evaluated: 62 (all non-rejected items). Published numbers use `--reviewed-only`.

nAI 0.6.0 at commit `ef1f971+dirty`; embeddings `ibm-granite/granite-embedding-97m-multilingual-r2` (fastembed); reranker `off`; 47 answerable + 15 unanswerable questions over 100 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| bm25 | 0.842 | 0.808 | 0.894 | 0.809 | 0.204 | 0.787 | 0.800 |
| embedding | 0.843 | 0.787 | 0.936 | 0.857 | 0.217 | 0.811 | 0.840 |
| hybrid | 0.834 | 0.766 | 0.915 | 0.856 | 0.221 | 0.806 | 0.840 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 14 | 0.714 | 0.599 |
| lookup | 12 | 1.000 | 1.000 |
| multi-hop | 11 | 1.000 | 0.849 |
| table/scan-OCR | 10 | 1.000 | 0.950 |
| *same language* | 33 | 1.000 | 0.934 |
| *question language ≠ source language* | 14 | 0.714 | 0.599 |

Hit@5 / MRR by question language (hybrid):

| Language | n | Hit@5 | MRR |
|---|---|---|---|
| de | 14 | 0.929 | 0.902 |
| en | 7 | 0.714 | 0.596 |
| fr | 10 | 1.000 | 0.933 |
| pt | 10 | 0.900 | 0.850 |
| sv | 6 | 1.000 | 0.764 |

Answerable questions with no result at all (embedding search drops hits below `NAI_EMBEDDINGS_MIN_SCORE`, cosine 0.3 by default):

| Method | same language: no result | question language ≠ source language: no result |
|---|---|---|
| bm25 | 0 of 33 | 0 of 14 |
| embedding | 0 of 33 | 0 of 14 |
| hybrid | 0 of 33 | 0 of 14 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.553 | 0.596 | 0.915 | 0.021 | 0.000 | 0.000 | 0.839 | – | – | 0.052 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
