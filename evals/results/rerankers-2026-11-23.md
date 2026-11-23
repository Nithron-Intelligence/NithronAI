# nai-bench reranker comparison – 2026-11-23

Candidates from nAI 0.5.0 (bench stack, reranker off, embeddings paraphrase-multilingual-MiniLM-L12-v2). Scored on a Ryzen 9 7950X limited to 2 threads, so latencies are optimistic for NAS CPUs; peak RAM is for a PyTorch process (st/qwen3 backends) or fastembed/onnxruntime (fastembed backend).

Each model re-scores the same top-30 hybrid candidates from nAI for 45 answerable questions, on 2 CPU threads (NAS-like). Document-level metrics; latency is per question (30 passages).

| Reranker | License | Params | MRR | Hit@1 | Hit@5 | Page Hit@5 | MRR cross-lingual | Median s | p90 s | Peak RAM MB |
|---|---|---|---|---|---|---|---|---|---|---|
| none (hybrid RRF order) | – | – | 0.793 | 0.667 | 0.933 | 0.773 | 0.650 | – | – | – |
| ms-marco-MiniLM-L-6 (current default) | Apache-2.0 | 22M | 0.791 | 0.689 | 0.956 | 0.727 | 0.483 | 0.665 | 1.255 | 1257 |
| bge-reranker-v2-m3 int8 | Apache-2.0 | 568M | 0.918 | 0.867 | 0.978 | 0.909 | 0.917 | 3.735 | 10.527 | 2622 |
| mmarco-mMiniLMv2-L12 | Apache-2.0 | 118M | 0.802 | 0.689 | 0.933 | 0.818 | 0.714 | 0.895 | 1.511 | 1442 |
| Qwen3-Reranker-0.6B | Apache-2.0 | 596M | 0.956 | 0.933 | 0.978 | 0.909 | 1.000 | 39.848 | 70.077 | 9359 |
| Alibaba-NLP/gte-multilingual-reranker-base (Apache-2.0, 306M) | not run: needs trust_remote_code (runs Python code from the model repository) and has no fastembed/ONNX build; we don't run remote code, so it can't be a Loupe base as published | | | | | | | | | |
| mixedbread-ai/mxbai-rerank-base-v2 (Apache-2.0, 494M) | not run: LLM-based (Qwen2 architecture) like Qwen3-Reranker but needs its own scoring library; not run | | | | | | | | | |
| jinaai/jina-reranker-v2-base-multilingual | not run: rejected: CC-BY-NC-4.0 (non-commercial) | | | | | | | | | |
| BAAI/bge-reranker-base | not run: rejected: Chinese and English only | | | | | | | | | |

Notes per model:

- **ms-marco-MiniLM-L-6 (current default)**: English-only; trained on MS MARCO (non-commercial data terms)
- **bge-reranker-v2-m3 int8**: multilingual (XLM-R); fastembed ships an int8 ONNX (0.57 GB)
- **mmarco-mMiniLMv2-L12**: 15 languages; trained on mMARCO (translated MS MARCO, non-commercial data terms)
- **Qwen3-Reranker-0.6B**: LLM-style yes/no scoring; 100+ languages

## How many candidates to rerank (bge-reranker-v2-m3 int8, 2 threads)

| Candidates reranked | MRR | Hit@1 | Hit@5 | Page Hit@5 | MRR cross-lingual | Median s | p90 s |
|---|---|---|---|---|---|---|---|
| top-10 | 0.878 | 0.822 | 0.933 | 0.773 | 0.857 | 2.08 | 2.891 |
| top-15 | 0.885 | 0.822 | 0.956 | 0.818 | 0.881 | 3.223 | 4.964 |
| top-30 | 0.918 | 0.867 | 0.978 | 0.909 | 0.917 | 3.735 | 10.527 |

Without reranking: MRR 0.793 (top-30 hybrid order). Latencies were measured on a Ryzen 9 7950X limited to 2 threads, partly while other jobs ran; a NAS CPU will be slower. Peak RAM for the PyTorch-based runs (mmarco, Qwen3 in fp32) is much higher than an ONNX build would need.
