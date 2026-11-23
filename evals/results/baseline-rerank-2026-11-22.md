# nai-bench baseline-rerank – 2026-11-22

> **Note (2026-11-23):** this run was recorded at commit `c9de9eb`, which a rebase onto the v0.5.0 release rewrote as `f81d16b` (same content). All nai-bench v0 items were **unreviewed** at the time, so these numbers are **PROVISIONAL** (see evals/nai-bench/README.md, Human review).

Same as the baseline with NAI_RERANKER=true (default reranker Xenova/ms-marco-MiniLM-L-6-v2, English-only); retrieval and extractive answers only. Stack: infra/compose.bench.yaml at this commit (Tesseract eng+deu, LLM temperature 0), Ollama 0.40.17-rocm on an AMD Radeon RX 7900 XTX (24 GB), host Ryzen 9 7950X. Judge: qwen2.5:7b (Apache-2.0). Latencies are for this GPU, not NAS hardware.

nAI 0.5.0 at commit `c9de9eb`; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed); reranker `true`; 45 answerable + 11 unanswerable questions over 27 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| hybrid | 0.791 | 0.689 | 0.956 | 0.911 | 0.218 | 0.794 | 0.727 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 10 | 0.900 | 0.476 |
| lookup | 16 | 1.000 | 1.000 |
| multi-hop | 9 | 1.000 | 0.861 |
| table/scan-OCR | 10 | 0.900 | 0.708 |
| *same language* | 31 | 0.968 | 0.930 |
| *question language ≠ source language* | 14 | 0.929 | 0.483 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.533 | 0.578 | 0.911 | 0.000 | 0.000 | 0.000 | 0.855 | – | – | 0.297 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
