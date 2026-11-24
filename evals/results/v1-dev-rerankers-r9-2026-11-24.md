# nai-bench reranker comparison – 2026-11-24

Round 9 reranker audit (2026-11-24). nai-bench v1 dev split, PROVISIONAL (no item human-reviewed). Candidates: nAI 0.7.0 (local build of 2e8e425) hybrid with granite-embedding-97m-multilingual-r2, reranker off; each model re-scores nAI's top 10 like NAI_RERANKER_CANDIDATES=10. CPU: Ryzen 9 7950X (Zen 4), 8 threads, run inside the ROCm trainer container with the GPU hidden.

Each model re-scores the same top-10 hybrid candidates from nAI for 47 answerable questions of `evals/nai-bench/v1/questions-dev.jsonl`, on 8 CPU threads. Document-level metrics; latency is per question (10 passages).

| Reranker | License | Params | MRR | Hit@1 | Hit@5 | Page Hit@5 | MRR cross-lingual | Hit@5 cross-lingual | Median s | p90 s | Peak RAM MB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none (hybrid RRF order) | – | – | 0.834 | 0.766 | 0.915 | 0.840 | 0.599 | 0.714 | – | – | – |
| bge-reranker-v2-m3 int8 | Apache-2.0 | 568M | 0.896 | 0.872 | 0.915 | 0.840 | 0.652 | 0.714 | 0.814 | 0.995 | 1600 |
| Horizon multilingual-reranker-small int8 | Apache-2.0 | 141M | 0.886 | 0.851 | 0.915 | 0.840 | 0.616 | 0.714 | 0.422 | 0.601 | 1760 |
| Horizon multilingual-reranker-base int8 | Apache-2.0 | 308M | 0.905 | 0.894 | 0.915 | 0.840 | 0.682 | 0.714 | 0.983 | 1.364 | 2544 |
| Qwen3-Reranker-0.6B | Apache-2.0 | 596M | 0.896 | 0.872 | 0.915 | 0.840 | 0.652 | 0.714 | 17.556 | 18.407 | 7682 |
| Alibaba-NLP/gte-multilingual-reranker-base (Apache-2.0, 306M) | not run: needs trust_remote_code (runs Python code from the model repository) and has no fastembed/ONNX build; we don't run remote code, so it can't be a Loupe base as published | | | | | | | | | | |
| mixedbread-ai/mxbai-rerank-base-v2 (Apache-2.0, 494M) | not run: LLM-based (Qwen2 architecture) like Qwen3-Reranker but needs its own scoring library; not run | | | | | | | | | | |
| jinaai/jina-reranker-v2-base-multilingual | not run: rejected: CC-BY-NC-4.0 (non-commercial) | | | | | | | | | | |
| BAAI/bge-reranker-base | not run: rejected: Chinese and English only | | | | | | | | | | |

Notes per model:

- **bge-reranker-v2-m3 int8**: multilingual (XLM-R); fastembed ships an int8 ONNX (0.57 GB)
- **Horizon multilingual-reranker-small int8**: mmBERT-small (ModernBERT); data: FineWeb/FineWeb-2, MIRACL train, WebFAQ, synthetic queries; labels distilled from Qwen3-Reranker-4B (round 9 audit)
- **Horizon multilingual-reranker-base int8**: mmBERT-base (ModernBERT); same data and teacher as the small model (round 9 audit)
- **Qwen3-Reranker-0.6B**: LLM-style yes/no scoring; 100+ languages
