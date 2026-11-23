# Model, data and tool license register

> Principle 2 of the [lab roadmap](ROADMAP.md): every base model, dataset, generator model and tool that
> the lab uses gets a row here **before** it is used. "Checked" means the license on the Hugging Face model
> card / project page was read on that date. Licenses change: re-check on the day you start a training run
> and update the date.
>
> Code dependencies of nAI itself follow the existing rule (no AGPL; see `NOTICE`); this register is for
> models, data and ML tooling.

Status values: **in use** (shipped or used by nAI today), **approved** (may be used), **candidate**
(looks fine, decide before use), **avoid** (don't use for the lab; reason given).

## Models used by nAI today

| Model | Role | License | Status | Checked | Notes |
|---|---|---|---|---|---|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | default embeddings (fastembed) | Apache-2.0 | in use | 2026-11-22 | 118M params, 384-d, 50+ languages. Stage 1 base candidate. |
| `Xenova/ms-marco-MiniLM-L-6-v2` (ONNX of `cross-encoder/ms-marco-MiniLM-L6-v2`) | default reranker (off unless `NAI_RERANKER`) | Apache-2.0 (upstream card; the Xenova repo states none) | in use | 2026-11-22 | **English-only**, trained on MS MARCO, whose terms are non-commercial research. Fine to run, but don't fine-tune from it or reuse MS MARCO; prefer a multilingual reranker (below). |
| `qwen2.5:1.5b` (`Qwen/Qwen2.5-1.5B-Instruct`) | LLM in the nai-bench stack and smoke test | Apache-2.0 | in use (bench) | 2026-11-22 | |
| `qwen2.5:7b` (`Qwen/Qwen2.5-7B-Instruct`) | optional LLM judge in the baseline | Apache-2.0 | in use (bench) | 2026-11-22 | Judge outputs are eval data only. |
| `llama3.2` | example model in `infra/docker-compose.yml` comment and `packages/model-router` | Llama 3.2 Community License | avoid for the lab | 2026-11-22 | Acceptable-use policy and naming rules for derivatives. Fine for a user to run; don't build Nithron models on it. |

## Candidates for Stage 1 (embeddings / reranker)

| Model | License | Status | Checked | Notes |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | MIT | candidate | 2026-11-22 | 118M, 384-d; needs "query:" / "passage:" prefixes. |
| `intfloat/multilingual-e5-base` | MIT | candidate | 2026-11-22 | 278M; probably too slow for low-end NAS CPUs. |
| `BAAI/bge-m3` | MIT | candidate (teacher / upper bound) | 2026-11-22 | 568M; too big as a NAS default, useful as a reference and for hard-negative mining. |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 | candidate | 2026-11-22 | Multilingual reranker; nAI already mentions its int8 ONNX as an option. |
| `jinaai/jina-reranker-v2-base-multilingual` | CC-BY-NC-4.0 | avoid | 2026-11-22 | Non-commercial. |

## Candidates for synthetic data generation (teacher models, principle 3)

Teacher outputs become training data, so the license must allow using outputs to train other models,
without naming or field-of-use restrictions on the result. `training/embed/common.py::APPROVED_TEACHERS`
must only list models from this table with status approved or candidate (a test checks it).

| Model | License | Status | Checked | Notes |
|---|---|---|---|---|
| `Qwen/Qwen2.5-7B-Instruct` (Ollama `qwen2.5:7b`) | Apache-2.0 | approved | 2026-11-22 | Runs on the local 24 GB GPU via Ollama; used for the Stage 1 smoke run. |
| `Qwen/Qwen3-14B`, `Qwen/Qwen3-30B-A3B` (Ollama `qwen3:14b`, `qwen3:30b-a3b`) | Apache-2.0 | candidate | 2026-11-22 | Better multilingual quality; 30B-A3B needs a Q4 quant on 24 GB. Disable "thinking" output (`--no-think`). |
| `mistralai/Mistral-Small-3.1-24B-Instruct-2503` (Ollama `mistral-small3.1`) | Apache-2.0 | candidate | 2026-11-22 | Strong European languages; Q4 on 24 GB. |
| `Qwen/Qwen2.5-3B-Instruct` | Qwen Research License | avoid | 2026-11-22 | Non-commercial (only 3B and 72B of Qwen2.5 have this license). |
| `google/gemma-3-*` | Gemma Terms of Use | avoid | 2026-11-22 | Terms extend to models trained on outputs; use policy restrictions. |
| `meta-llama/Llama-3.*` | Llama Community License | avoid | 2026-11-22 | Naming requirement and AUP on derivatives. |
| Claude, GPT and other hosted frontier APIs | provider terms | **never for training data** | 2026-11-22 | Terms forbid using outputs to build competing models. Eval items written with Claude are marked `"author": "claude", "use": "eval-only"`. |

## Candidates for Stage 2 (1–4B answering model)

| Model | License | Status | Checked | Notes |
|---|---|---|---|---|
| `Qwen/Qwen2.5-1.5B-Instruct` | Apache-2.0 | candidate | 2026-11-22 | The current bench baseline. |
| `Qwen/Qwen3-1.7B`, `Qwen/Qwen3-4B` | Apache-2.0 | candidate | 2026-11-22 | |
| `HuggingFaceTB/SmolLM3-3B` | Apache-2.0 | candidate | 2026-11-22 | Multilingual coverage of SV/PT to be checked on nai-bench. |
| `microsoft/Phi-4-mini-instruct` | MIT | candidate | 2026-11-22 | 3.8B. |

## Training-data lineage of base models

The licenses above are the model licenses. What a base model was itself trained on is a separate
question: `paraphrase-multilingual-MiniLM-L12-v2` was distilled on public parallel and paraphrase data, and
`multilingual-e5-*` on a large web-mined mix. Their model licenses allow fine-tuning and redistribution
under Apache-2.0/MIT; we have **not** audited their training data. Model cards we release must say so.

## Datasets and corpora

| Dataset | License | Status | Notes |
|---|---|---|---|
| nai-bench corpus, fictional documents (`evals/nai-bench/corpus-src/*`) | CC0-1.0 | in use (eval) | Written for nai-bench by Claude, fictional people and companies. Eval-only (principle 3). |
| nai-bench `Gesetze/BGB_Mietrecht_Auszug.txt` | public domain (§ 5 Abs. 1 UrhG, amtliches Werk) | in use (eval) | From gesetze-im-internet.de, 2026-11-22. |
| nai-bench `Gesetze/Jordabalken_12kap_utdrag.txt` | public domain (9 § upphovsrättslagen) | in use (eval) | From data.riksdagen.se, 2026-11-22. |
| nai-bench questions (`evals/nai-bench/questions.jsonl`) | CC0-1.0 | in use (eval) | Claude-authored, `use: eval-only`; never in training. |
| MS MARCO | Microsoft terms: non-commercial research | avoid | Many English retrieval models are trained on it; don't add it to our data. |
| Stage 1 synthetic pairs | to be released as CC-BY-4.0 or CC0 | planned | Generated by an approved teacher from a separately generated corpus. |

## Tools

| Tool | License | Use |
|---|---|---|
| sentence-transformers | Apache-2.0 | Stage 1 training |
| PyTorch | BSD-3-Clause | Stage 1/2 training |
| transformers, peft, optimum | Apache-2.0 | training, LoRA, ONNX export |
| onnxruntime | MIT | ONNX export check, fastembed runtime |
| fastembed | Apache-2.0 | nAI embeddings runtime |
| Ollama | MIT | local LLM serving, teacher model serving |
| llama.cpp | MIT | GGUF export (Stage 2) |
| Tesseract | Apache-2.0 | OCR in nAI |
| reportlab | BSD-3-Clause | builds the nai-bench PDFs (build time only) |
| python-docx | MIT | builds the nai-bench DOCX files (build time only) |
| Pillow | MIT-CMU (HPND) | renders the nai-bench scans (build time only) |
