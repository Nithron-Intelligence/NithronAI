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
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | default embeddings up to 0.6.0 (fastembed) | Apache-2.0 | replaced (default until 0.6.0; lineage has non-commercial data, see the audit) | 2026-11-22 | 118M params, 384-d, 50+ languages. Stage 1 base candidate. |
| `Xenova/ms-marco-MiniLM-L-6-v2` (ONNX of `cross-encoder/ms-marco-MiniLM-L6-v2`) | default reranker model (reranking is **off by default** since 2026-11-23) | Apache-2.0 (upstream card; the Xenova repo states none) | in use | 2026-11-22 | **English-only**, trained on MS MARCO, whose terms are non-commercial research. Fine to run, but don't fine-tune from it or reuse MS MARCO; prefer a multilingual reranker (below). |
| `qwen2.5:1.5b` (`Qwen/Qwen2.5-1.5B-Instruct`) | LLM in the nai-bench stack and smoke test | Apache-2.0 | in use (bench) | 2026-11-22 | |
| `qwen2.5:7b` (`Qwen/Qwen2.5-7B-Instruct`) | optional LLM judge in the baseline | Apache-2.0 | in use (bench) | 2026-11-22 | Judge outputs are eval data only. |
| `llama3.2` | example model in the `infra/docker-compose.yml` comment | Llama 3.2 Community License | avoid for the lab | 2026-11-22 | Acceptable-use policy and naming rules for derivatives. Fine for a user to run; don't build Nithron models on it. |

## Candidates for Stage 1 (embeddings / reranker)

| Model | License | Status | Checked | Notes |
|---|---|---|---|---|
| `ibm-granite/granite-embedding-97m-multilingual-r2` | Apache-2.0 (model card, not gated; checked 2026-11-23) | **in use: nAI default embeddings from 0.7.0 (Unreleased) and Vane 1 base** (human decision 2026-11-23; switch criteria met on v1 dev) | 2026-11-23 | ModernBERT (`ModernBertModel`, built into transformers; no `.py` in the repo, **no trust_remote_code**); sentence-transformers library; 97M params, **384-d**, **CLS pooling**, **no query/passage prefix** (prompts empty), max length 32 768, 180k-token vocab; 52 enhanced languages incl. **de, en, fr, pt, sv**. Repo ships `onnx/model.onnx` (390 MB) and `onnx/model_quint8_avx2.onnx` (98 MB) under the same card. Training data: MS MARCO excluded for its non-commercial license (R2 paper, arXiv 2605.13521); audit in `vane1-base-model-audit.md`. fastembed custom model (CLS) parity vs PyTorch: fp32 1.0000, int8 0.9723. |
| `ibm-granite/granite-embedding-311m-multilingual-r2` | Apache-2.0 (model card, checked 2026-11-23) | candidate (comparison) | 2026-11-23 | ModernBERT, 311M, 768-d (Matryoshka 768/512/384/256/128), CLS pooling, no prefix, max length 32 768, same languages and training-data statement as the 97m; ONNX in the repo. |
| `intfloat/multilingual-e5-small` | MIT | candidate | 2026-11-22 | 118M, 384-d; needs "query:" / "passage:" prefixes. |
| `intfloat/multilingual-e5-base` | MIT | candidate | 2026-11-22 | 278M; probably too slow for low-end NAS CPUs. |
| `BAAI/bge-m3` | MIT | candidate (teacher / upper bound) | 2026-11-22 | 568M; too big as a NAS default, useful as a reference and for hard-negative mining. |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 (model card, checked 2026-11-23) | **fails the lineage check** (MS MARCO, non-commercial, in its and bge-m3's training data): still the default *model*, but `NAI_RERANKER=auto` no longer turns it on (decision 2026-11-26, from 0.8.0); `on` runs it at the admin's choice. The int8 ONNX repo (`onnx-community/bge-reranker-v2-m3-ONNX`) states no license. | 2026-11-26 | Replace once a cleared reranker exists (Loupe 1). |
| `Qwen/Qwen3-Reranker-0.6B` | Apache-2.0 (model card, checked 2026-11-23) | **fails the lineage check** (MS MARCO in the supervised data): not a Loupe 1 teacher (decision 2026-11-26) | 2026-11-26 | |
| `Horizon-Labs/multilingual-reranker-small`, `-base` | Apache-2.0 (model cards, checked 2026-11-24) | evaluated (bench only); **not adopted** (decision 2026-11-26): its labels are distilled from Qwen3-Reranker-4B, whose series lists MS MARCO | 2026-11-26 | mmBERT-small/base (MIT). Data: FineWeb/FineWeb-2 (ODC-BY), MIRACL train (Apache-2.0), WebFAQ (CC-BY-4.0, small only), synthetic queries; labels distilled from `Qwen3-Reranker-4B`. Own int8 ONNX. |
| `ibm-granite/granite-embedding-reranker-english-r2` | Apache-2.0 (model card, checked 2026-11-24) | reference only | 2026-11-24 | Clean (excludes MS MARCO explicitly) but English only; no multilingual Granite reranker exists. |
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Apache-2.0 (model); trained on mMARCO (MS MARCO translations, non-commercial terms) | avoid | 2026-11-23 | Small gain only (MRR 0.802) and a data-lineage risk. |
| `Alibaba-NLP/gte-multilingual-reranker-base` | Apache-2.0 | not usable as published | 2026-11-23 | Needs `trust_remote_code` (runs code from the model repo) and has no ONNX build; we don't run remote code. |
| `jinaai/jina-reranker-v2-base-multilingual` | CC-BY-NC-4.0 | avoid | 2026-11-22 | Non-commercial. |

## Candidates for synthetic data generation (teacher models, principle 3)

Teacher outputs become training data, so the license must allow using outputs to train other models,
without naming or field-of-use restrictions on the result. `training/embed/common.py::APPROVED_TEACHERS`
must only list models from this table with status approved or candidate (a test checks it).

| Model | License | Status | Checked | Notes |
|---|---|---|---|---|
| `Qwen/Qwen2.5-7B-Instruct` (Ollama `qwen2.5:7b`) | Apache-2.0 | approved | 2026-11-22 | Runs on the local 24 GB GPU via Ollama; used for the Stage 1 smoke run. |
| `Qwen/Qwen3-14B`, `Qwen/Qwen3-30B-A3B` (Ollama `qwen3:14b`, `qwen3:30b-a3b`) | Apache-2.0 | candidate | 2026-11-22 | Better multilingual quality; 30B-A3B needs a Q4 quant on 24 GB. Disable "thinking" output (`--no-think`). |
| `mistralai/Mistral-Small-3.1-24B-Instruct-2503` (Ollama `mistral-small3.1`) | Apache-2.0 (model card `license: apache-2.0`, not gated, re-checked 2026-11-23) | approved | 2026-11-23 | **Vane 1 teacher** (human decision 2026-11-23). Ollama `mistral-small3.1:latest` = 24B **Q4_K_M**, 15 GB on disk, leaving ~9 GB of the 24 GB RX 7900 XTX for context (run with an 8k context). Deliberately not the bench judge (`qwen2.5:7b`). |
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
| `microsoft/Phi-4-mini-instruct` (Ollama `phi4-mini`) | MIT (model card, checked 2026-11-23) | **in use (bench): second answering LLM in the Stage 0 baseline** | 2026-11-23 | 3.8B, Ollama Q4_K_M 2.5 GB. Chosen over Qwen3-1.7B/4B because nAI doesn't strip Qwen3's thinking output. |

## Data rule for Vane 1 training data (human decision 2026-11-23)

No CC-BY-SA material. Allowed: public domain, CC0, CC-BY, EU reuse texts (Commission Decision 2011/833/EU) and
text generated by an approved teacher. Every training input passes `common.read_training_rows` (no eval-only,
Claude-written or nai-bench rows) and `check_overlap.py` against all nai-bench files and questions.

## Training-data lineage of base models

Vane 1's base, `paraphrase-multilingual-MiniLM-L12-v2`: audited on 2026-11-23. Verdict: **needs the human's decision**: its teacher was trained on MS MARCO and Flickr30k captions
(non-commercial terms) and on CC-BY-SA data.


The licenses above are the model licenses. What a base model was itself trained on is a separate
question: `paraphrase-multilingual-MiniLM-L12-v2` was distilled on public parallel and paraphrase data, and
`multilingual-e5-*` on a large web-mined mix. Their model licenses allow fine-tuning and redistribution
under Apache-2.0/MIT; we have **not** audited their training data. Model cards we release must say so.

**Open item (Vane 1 release blocker):** audit the training data of `paraphrase-multilingual-MiniLM-L12-v2`
(Vane 1 base) and `multilingual-e5-small` (comparison), and of the Loupe 1 base: list the datasets and
their terms here, flag anything non-commercial, and record the outcome in the model card.

## Datasets and corpora

| Dataset | License | Status | Notes |
|---|---|---|---|
| nai-bench corpus, fictional documents (`evals/nai-bench/corpus-src/*`) | CC-BY-4.0 | in use (eval) | Written for nai-bench by Claude, fictional people and companies. Eval-only (principle 3). |
| nai-bench `Gesetze/BGB_Mietrecht_Auszug.txt` | public domain (§ 5 Abs. 1 UrhG, amtliches Werk) | in use (eval) | From gesetze-im-internet.de, 2026-11-22. |
| nai-bench `Gesetze/Jordabalken_12kap_utdrag.txt` | public domain (9 § upphovsrättslagen) | in use (eval) | From data.riksdagen.se, 2026-11-22. |
| nai-bench questions (`evals/nai-bench/questions.jsonl`) | CC-BY-4.0 | in use (eval) | Claude-authored, `use: eval-only`; never in training. |
| MS MARCO | Microsoft terms: non-commercial research | avoid | Many English retrieval models are trained on it; don't add it to our data. |
| Stage 1 synthetic pairs | to be released as CC-BY-4.0 or CC0 | planned | Generated by an approved teacher from a separately generated corpus. |
| Vane 1 round-9 public texts (`training/sources/vane1-data-v1.json`) | EU: CC BY 4.0 / Decision 2011/833/EU (attribution "© European Union"); DE statutes: § 5 Abs. 1 UrhG; SE statutes: 9 § URL; US CFR: 17 U.S.C. § 105 | in use (training data) | 2026-11-24: Sources verified on official pages ([data plan](vane1-data-plan.md)); none of them is a nai-bench document (checked by URL at download). |
| DGT Translation Memory | Commission Decision of 12 Dec 2011 (free, non-exclusive) | candidate | 2026-11-24: Re-use must state source URL, update date and "the European Commission retains ownership of the data". |
| Europarl (statmt.org) | no license granted ("not aware of any copyright restrictions") | avoid | 2026-11-24: Treat as unlicensed. |
| Project Gutenberg books (authors died before 1956) | public domain; PG trademark/license terms | candidate | 2026-11-24: PG policy pages answered 503 on 2026-11-24: re-read before the first download; strip header/licence; never a book nai-bench uses. |

## Tools

| Tool | License | Use |
|---|---|---|
| sentence-transformers | Apache-2.0 | Stage 1 training |
| PyTorch | BSD-3-Clause | Stage 1/2 training |
| transformers, peft, optimum | Apache-2.0 | training, LoRA, ONNX export |
| onnxruntime | MIT | ONNX export check, fastembed runtime |
| fastembed | Apache-2.0 | nAI embeddings runtime |
| websockets | BSD-3-Clause | nAI TrueNAS API client (also a uvicorn[standard] dependency) |
| Ollama | MIT | local LLM serving, teacher model serving |
| llama.cpp | MIT | GGUF export (Stage 2) |
| Tesseract | Apache-2.0 | OCR in nAI |
| reportlab | BSD-3-Clause | builds the nai-bench PDFs (build time only) |
| python-docx | MIT | builds the nai-bench DOCX files (build time only) |
| Pillow | MIT-CMU (HPND) | renders the nai-bench scans (build time only) |
