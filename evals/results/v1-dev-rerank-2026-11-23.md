# nai-bench v1-dev-rerank – 2026-11-23

nai-bench v1 **dev split** (62 items), PROVISIONAL: no v1 item is human-reviewed. Reranker **on** (BAAI/bge-reranker-v2-m3-int8, top 10), answering LLM qwen2.5:1.5b. Stack: infra/compose.bench.yaml with nai-core 0.6.0 (local build of 06c29e0 = the published v0.6.0) indexing evals/nai-bench/v1/corpus (100 files), Ollama 0.40.17-rocm on an AMD Radeon RX 7900 XTX (24 GB); judge qwen2.5:7b; LLM temperature 0.

**PROVISIONAL — includes unreviewed items.** Review: 0 of 62 items human-reviewed (0 rejected); evaluated: 62 (all non-rejected items). Published numbers use `--reviewed-only`.

nAI 0.6.0 at commit `0c941ad`; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed); reranker `on`; 47 answerable + 15 unanswerable questions over 100 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| bm25 | 0.879 | 0.872 | 0.894 | 0.831 | 0.213 | 0.831 | 0.800 |
| embedding | 0.580 | 0.532 | 0.617 | 0.585 | 0.149 | 0.564 | 0.520 |
| hybrid | 0.911 | 0.894 | 0.936 | 0.875 | 0.230 | 0.866 | 0.840 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 14 | 0.786 | 0.702 |
| lookup | 12 | 1.000 | 1.000 |
| multi-hop | 11 | 1.000 | 1.000 |
| table/scan-OCR | 10 | 1.000 | 1.000 |
| *same language* | 33 | 1.000 | 1.000 |
| *question language ≠ source language* | 14 | 0.786 | 0.702 |

Hit@5 / MRR by question language (hybrid):

| Language | n | Hit@5 | MRR |
|---|---|---|---|
| de | 14 | 0.929 | 0.929 |
| en | 7 | 0.857 | 0.857 |
| fr | 10 | 1.000 | 1.000 |
| pt | 10 | 0.900 | 0.833 |
| sv | 6 | 1.000 | 0.917 |

Answerable questions with no result at all (embedding search drops hits below `NAI_EMBEDDINGS_MIN_SCORE`, cosine 0.3 by default):

| Method | same language: no result | question language ≠ source language: no result |
|---|---|---|
| bm25 | 0 of 33 | 0 of 14 |
| embedding | 0 of 33 | 0 of 14 |
| hybrid | 0 of 33 | 0 of 14 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.575 | 0.617 | 0.894 | 0.000 | 0.000 | 0.000 | 0.820 | – | – | 0.964 |
| llm: ollama/qwen2.5:1.5b | 0.596 | 0.617 | 0.894 | 0.043 | 0.064 | 0.400 | 0.600 | 0.685 | 0.863 | 1.190 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
