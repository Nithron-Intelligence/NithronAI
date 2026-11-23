# nai-bench baseline-rerank-bge – 2026-11-23

In-app check of the proposed Loupe 1 base: nAI with NAI_RERANKER=true and NAI_RERANKER_MODEL=BAAI/bge-reranker-v2-m3-int8 (top-30 candidates, nai-core on a Ryzen 9 7950X without CPU limits). Compare with baseline-2026-11-22 (hybrid MRR 0.793).

**PROVISIONAL — includes unreviewed items.** Review: 0 of 56 items human-reviewed (0 rejected); evaluated: 56 (all non-rejected items). Published numbers use `--reviewed-only`.

nAI 0.5.0 at commit `c51226f+dirty`; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed); reranker `true`; 45 answerable + 11 unanswerable questions over 27 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| hybrid | 0.918 | 0.867 | 0.978 | 0.944 | 0.227 | 0.908 | 0.909 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 10 | 1.000 | 0.950 |
| lookup | 16 | 1.000 | 0.938 |
| multi-hop | 9 | 1.000 | 0.926 |
| table/scan-OCR | 10 | 0.900 | 0.850 |
| *same language* | 31 | 0.968 | 0.919 |
| *question language ≠ source language* | 14 | 1.000 | 0.917 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.644 | 0.700 | 0.978 | 0.000 | 0.000 | 0.000 | 0.636 | – | – | 1.183 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
