# ADR-0002: Nithron AI lab direction

- Status: accepted (2026-11-22; direction set by the maintainer)
- Supersedes: nothing; extends the product direction in the README roadmap

## Context

nAI is a self-hosted retrieval and question-answering service for NAS folders (hybrid BM25 + multilingual
semantic search, OCR, cited answers, OpenAI-compatible API, MCP server). Up to v0.5 it trains nothing: it
uses pretrained models as they are (fastembed `paraphrase-multilingual-MiniLM-L12-v2`, an optional
English cross-encoder reranker, any LLM via LiteLLM/Ollama). Its retrieval eval had five placeholder
questions and there was no answer-quality eval, so we could not say whether a change made answers better.

The models that matter for nAI are small: an embedding model, a reranker, a 1–4B answering model and,
later, an agent model for NithronOS. They must run on NAS-class hardware (a few GB of RAM, often no GPU)
and handle private, multilingual files. Large labs don't optimize for that.

## Decision

1. Nithron AI becomes a small lab that builds private, local models for NAS-class hardware, starting with
   the models nAI uses. nAI is the product; NithronOS is the distribution channel.
2. Work follows the staged path in [docs/lab/ROADMAP.md](../lab/ROADMAP.md): measurement (nai-bench) first,
   then an embedding model, then a small answering model, then a NithronOS agent model.
3. Four principles are binding (see the roadmap for the full text): no training on users' data without
   explicit opt-in; every model, dataset and tool license is checked and recorded before use; no training
   data from services whose terms forbid it (including Claude), with a `provenance` field on every item;
   every model claim is backed by a nai-bench number.
4. nai-bench lives in this repo (`evals/nai-bench/`), is released under CC0-1.0 and is never used as
   training data.
5. Training code lives in `training/` and is not a dependency of nai-core: the nAI image keeps its
   "no PyTorch" property.

## Consequences

- Every retrieval or answering change can now be measured; results files with pinned settings go in
  `evals/results/`.
- New work items: grow nai-bench to v1 with a test split and human review; a license register
  (`docs/lab/MODEL_AND_DATA_LICENSES.md`); a synthetic-data pipeline that uses open-weight models only.
- nAI's own product roadmap (README) continues; the lab roadmap feeds it models.
- Costs: Stage 1 fits on the existing workstation GPU; Stage 2 may need rented GPU time; Stage 4 needs
  someone to own releases on Hugging Face.
- Risk: the lab could pull time away from shipping nAI to NithronOS users. Mitigation: each stage must ship
  something nAI uses (a model it can switch to, or a measurement it relies on).
