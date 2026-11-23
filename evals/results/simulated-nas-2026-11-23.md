# nAI on NAS-class hardware (SIMULATED NAS) – 2026-11-23

**Environment: SIMULATED NAS.** Profile nas-small: nai-core limited to 2 CPUs / 4 GiB and Ollama to 2 CPUs / 4 GiB (CPU only, qwen2.5:1.5b), with docker --cpus/--memory on a Ryzen 9 7950X host (about an Intel N100-class box with 8 GB RAM, but each core here is faster).

Simulated means a desktop CPU limited with Docker (`--cpus`, `--memory`); one desktop core is considerably faster than a typical NAS core, so real NAS numbers will be slower.

nAI 0.5.0, embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, reranker `false`, OCR on. nai-bench corpus: 27 files, 78 chunks.

| Measurement | Value |
|---|---|
| Indexing from scratch (scan + OCR + embeddings) | 26.9 s |
| Search (hybrid), median / p95 | 0.2 s / 0.399 s |
| Extractive answer, median / p95 | 0.199 s / 0.301 s |
| LLM answer (10 questions, `ollama/qwen2.5:1.5b`): time to first token, median | 0.4 s |
| LLM answer: total, median / p95 | 4.693 s / 21.301 s |
| LLM streaming speed, median | 6.4 token events/s |

Memory and CPU per phase (docker stats, sampled every 0.5 s):

| Container | Phase | Peak memory (MiB) | Mean CPU % |
|---|---|---|---|
| nai-bench-nai-core-1 | 2-indexing | 1138 | 196 |
| nai-bench-nai-core-1 | 3-idle-after-indexing | 997 | 0 |
| nai-bench-nai-core-1 | 4-search | 1001 | 176 |
| nai-bench-nai-core-1 | 5-extractive-answers | 996 | 199 |
| nai-bench-nai-core-1 | 6-llm-answers | 1044 | 23 |
| nai-bench-ollama-1 | 2-indexing | 1590 | 0 |
| nai-bench-ollama-1 | 3-idle-after-indexing | 1590 | 0 |
| nai-bench-ollama-1 | 4-search | 1590 | 0 |
| nai-bench-ollama-1 | 5-extractive-answers | 1590 | 0 |
| nai-bench-ollama-1 | 6-llm-answers | 1592 | 191 |
