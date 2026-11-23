# Granite Embedding R2 vs today's default on nai-bench v1 dev – 2026-11-23

**PROVISIONAL.** v1 **dev split only** (62 items, 47 answerable), no item human-reviewed, one run each. With 47
answerable questions the 95 % margin on MRR is roughly ±0.09. Models: today's default
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (mean pooling), `ibm-granite/granite-embedding-97m-
multilingual-r2` and `-311m-` (CLS pooling, **no prefix**: both models' sentence-transformers prompts are empty).

## In nAI (bench stack, fastembed, reranker off, no LLM)

Run files: [MiniLM](v1-dev-emb-minilm-2026-11-23.md), [granite 97m](v1-dev-emb-granite97-2026-11-23.md). Granite
311m was stopped after 15 % of the 10 462-chunk index (about 100 chunks/min on CPU, ~1.5 h): not a NAS candidate,
measured offline below instead.

| Model | Method | MRR | Hit@5 | same-language Hit@5 / MRR (n = 33) | cross-language Hit@5 / MRR (n = 14) |
|---|---|---|---|---|---|
| MiniLM | embedding | 0.494 | 0.575 | 0.545 / 0.450 | 0.643 / 0.597 |
| granite 97m | embedding | **0.843** | **0.936** | 1.000 / 0.881 | **0.786 / 0.752** |
| MiniLM | hybrid | 0.720 | 0.894 | 0.970 / 0.779 | 0.714 / 0.582 |
| granite 97m | hybrid | **0.834** | **0.915** | 1.000 / 0.934 | 0.714 / 0.599 |

Per language, hybrid Hit@5 / MRR, MiniLM → granite 97m: de 0.93/0.71 → 0.93/0.90; en 0.57/0.60 → 0.71/0.60;
fr 1.00/0.82 → 1.00/0.93; pt 0.90/0.80 → 0.90/0.85; **sv 1.00/0.58 → 1.00/0.76**. Per category, hybrid MRR:
lookup 1.00 → 1.00, multi-hop 0.70 → 0.85, table/scan-OCR 0.60 → 0.95, cross-lingual 0.58 → 0.60.

With granite, embedding-only beats hybrid on cross-language questions (Hit@5 0.786 vs 0.714): BM25 fusion now
dilutes the embedding ranking there. Worth a fusion-weight experiment on dev later (not tuned here).

## Offline, embedding only, same harness for all (`evals/embeddings/dense_eval.py`, 47 answerable)

| Model | MRR | Hit@1 | Hit@5 | cross-language Hit@5 / MRR | sv MRR |
|---|---|---|---|---|---|
| MiniLM | 0.444 | 0.362 | 0.532 | 0.571 / 0.435 | 0.333 |
| vane-1-rc0 (MiniLM pilot) | 0.613 | 0.489 | 0.766 | 0.857 / 0.676 | 0.525 |
| granite 97m | 0.854 | 0.787 | 0.979 | 0.929 / 0.735 | 0.917 |
| granite 311m | 0.938 | 0.894 | 1.000 | 1.000 / 0.911 | 1.000 |

## Simulated NAS (2 CPUs / 4 GB, `infra/compose.bench.nas-sim.yaml`, v0 corpus: 27 files, 78 chunks)

Run files: [MiniLM](simulated-nas-minilm-2026-11-23.md), [granite 97m](simulated-nas-granite97-2026-11-23.md).

| | MiniLM | granite 97m |
|---|---|---|
| Indexing from scratch (scan, OCR, embeddings) | 36 s | 65 s |
| Hybrid search median / p95 | 0.30 / 0.50 s | **0.20 / 0.30 s** |
| nai-core RAM: peak while indexing / idle after | 993 / 812 MiB | 1 625 / 1 444 MiB |
| Index on disk (`nai.db`) | 356 KB | 356 KB (both 384-d) |
| Model files on disk | 246 MB | 406 MB (fp32 ONNX; int8 not used, parity 0.972) |

## Switch criteria for granite 97m (human's round-6 decision)

- Overall hybrid MRR no worse beyond noise: 0.720 → 0.834 (better). **Met.**
- Cross-language Hit@5 no worse beyond noise: hybrid 0.714 → 0.714 (equal), embedding 0.643 → 0.786. **Met.**
- No language clearly worse: every language equal or better (Swedish MRR 0.58 → 0.76). **Met.**
- NAS latency and RAM acceptable: search 0.2 s median, well inside the ~1 s per-question budget of the reranker
  policy; +0.6 GB RAM (1.4 GB idle) fits the 4 GB profile; indexing ~1.8× slower. **Met, with the RAM and
  indexing-time cost noted** (a one-time re-index of a large NAS takes correspondingly longer).
