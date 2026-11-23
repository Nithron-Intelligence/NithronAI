# nAI on NAS-class hardware (SIMULATED NAS) – 2026-11-23

**Environment: SIMULATED NAS.** nai-core 2 CPUs / 2 GB (NAI_EMBEDDINGS=auto → keyword-only), reranker off, no LLM; Ryzen 9 7950X host

Simulated means a desktop CPU limited with Docker (`--cpus`, `--memory`); one desktop core is considerably faster than a typical NAS core, so real NAS numbers will be slower.

nAI 0.6.0, embeddings off (keyword-only; auto, off: 2 GB RAM: semantic search needs 2.5+ GB (3+ recommended), keyword search only), reranker `off`, OCR on. nai-bench corpus: 27 files, 78 chunks.

| Measurement | Value |
|---|---|
| Indexing from scratch (scan + OCR + embeddings) | 4.0 s |
| Search (bm25), median / p95 | 0.002 s / 0.002 s |
| Extractive answer, median / p95 | 0.002 s / 0.002 s |

Memory and CPU per phase (docker stats, polled continuously, about every 1–2 s):

The search phase (47 queries at ~2 ms) ended between two `docker stats` samples, so it has no row; the
extractive-answer phase after it peaked at 142 MiB.

| Container | Phase | Peak memory (MiB) | Mean CPU % |
|---|---|---|---|
| nai-bench-nai-core-1 | 2-indexing | 143 | 74 |
| nai-bench-nai-core-1 | 3-idle-after-indexing | 142 | 2 |
| nai-bench-nai-core-1 | 5-extractive-answers | 142 | 21 |
| nai-bench-ollama-1 | 2-indexing | 18 | 0 |
| nai-bench-ollama-1 | 3-idle-after-indexing | 18 | 0 |
| nai-bench-ollama-1 | 5-extractive-answers | 18 | 0 |
