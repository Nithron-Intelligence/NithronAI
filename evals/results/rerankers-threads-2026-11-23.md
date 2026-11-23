# Reranker latency vs CPU threads – 2026-11-23

**PROVISIONAL — nai-bench v0 items are unreviewed.** `BAAI/bge-reranker-v2-m3-int8` (fastembed, CPU build of onnxruntime) re-scoring the top 10 hybrid candidates for 45 answerable questions, on an AMD Ryzen 9 7950X with the thread count limited per run. A NAS core is slower than a Zen 4 core, so real NAS latency is higher.

| Threads | Median s per question | p90 s | MRR | Source |
|---|---|---|---|---|
| 2 | 2.08 | 2.891 | 0.878 | rerankers-2026-11-23 (round 2) |
| 4 | 1.092 | 1.521 | 0.878 | measured 2026-11-23 (round 3) |
| 8 | 0.699 | 1.003 | 0.878 | measured 2026-11-23 (round 3) |

Peak process RAM was about 1.5 GB (Python + onnxruntime + the 0.57 GB int8 model). This sets nAI's reranker auto threshold (8 effective cores, see `apps/nai-core/app/hardware.py`).
