# nai-bench reference-qwen2.5-7b – 2026-11-22

Reference: same stack and retrieval as the baseline, answering LLM qwen2.5:7b (too big for most NAS CPUs; shows the gap a small fine-tuned model should close). The judge is the same model as the answerer here, so its scores are likely biased upward. Stack: infra/compose.bench.yaml at this commit (Tesseract eng+deu, LLM temperature 0), Ollama 0.40.17-rocm on an AMD Radeon RX 7900 XTX (24 GB), host Ryzen 9 7950X. Judge: qwen2.5:7b (Apache-2.0). Latencies are for this GPU, not NAS hardware.

nAI 0.5.0 at commit `c9de9eb`; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed); reranker `false`; 45 answerable + 11 unanswerable questions over 27 files.

## Retrieval (document level)

| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |
|---|---|---|---|---|---|---|---|
| hybrid | 0.793 | 0.667 | 0.933 | 0.889 | 0.213 | 0.801 | 0.773 |

Hit@5 / MRR by category (hybrid):

| Category | n | Hit@5 | MRR |
|---|---|---|---|
| cross-lingual | 10 | 0.900 | 0.677 |
| lookup | 16 | 1.000 | 0.969 |
| multi-hop | 9 | 1.000 | 0.815 |
| table/scan-OCR | 10 | 0.800 | 0.610 |
| *same language* | 31 | 0.935 | 0.858 |
| *question language ≠ source language* | 14 | 0.929 | 0.650 |

## Answers

| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | Correct refusal | Language match | Judge correct | Judge grounded | Median s |
|---|---|---|---|---|---|---|---|---|---|---|
| extractive | 0.533 | 0.578 | 0.911 | 0.000 | 0.000 | 0.000 | 0.870 | – | – | 0.007 |
| llm: ollama/qwen2.5:7b | 0.822 | 0.844 | 0.911 | 0.044 | 0.111 | 0.727 | 0.852 | 0.964 | 0.946 | 0.552 |

Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.
Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,
except Language match (all questions).
Judge scores are normalized to 0–1 and only present when a judge model was given.
