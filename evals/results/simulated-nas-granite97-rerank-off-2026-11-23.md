# nAI on NAS-class hardware (SIMULATED NAS) – 2026-11-23

**Environment: SIMULATED NAS.** nai-core 2 CPUs / 4 GB, granite 97m (fp32 ONNX), reranker off (forced), no LLM; Ryzen 9 7950X host

Simulated means a desktop CPU limited with Docker (`--cpus`, `--memory`); one desktop core is considerably faster than a typical NAS core, so real NAS numbers will be slower.

nAI 0.6.0, embeddings `ibm-granite/granite-embedding-97m-multilingual-r2`, reranker `off`, OCR on. nai-bench corpus: 27 files, 78 chunks.

| Measurement | Value |
|---|---|
| Indexing from scratch (scan + OCR + embeddings) | 67.6 s |
| Search (hybrid), median / p95 | 0.2 s / 0.403 s |
| Extractive answer, median / p95 | 0.2 s / 0.299 s |

Memory and CPU per phase (docker stats, polled continuously, about every 1–2 s):

| Container | Phase | Peak memory (MiB) | Mean CPU % |
|---|---|---|---|
| nai-bench-nai-core-1 | 2-indexing | 1759 | 199 |
| nai-bench-nai-core-1 | 3-idle-after-indexing | 1625 | 0 |
| nai-bench-nai-core-1 | 4-search | 1625 | 198 |
| nai-bench-nai-core-1 | 5-extractive-answers | 1627 | 189 |
| nai-bench-ollama-1 | 2-indexing | 16 | 0 |
| nai-bench-ollama-1 | 3-idle-after-indexing | 15 | 0 |
| nai-bench-ollama-1 | 4-search | 15 | 0 |
| nai-bench-ollama-1 | 5-extractive-answers | 15 | 0 |
