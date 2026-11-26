# Nithron AI lab roadmap

> Status: accepted 2026-11-22 (stages and exit criteria will be refined). Decision record: [ADR-0002](../ADRs/0002-nithron-ai-lab-direction.md).
> Every model claim in this document and in any release must point to a nai-bench result file in
> [`evals/results/`](../../evals/results/).

## Vision

Nithron AI is a small lab that builds **private, local models that run on your own hardware**, starting
with the models nAI itself needs. nAI ("the AI that knows your NAS") is the product and runs on any NAS
OS ([ADR-0004](../ADRs/0004-nas-adapter-layer.md)); NithronOS is the reference platform and the first
distribution channel; retrieval over your own files is the core pipeline. The models are the
[Nithron model families](MODEL_NAMING.md): **Vane** (embeddings) → **Loupe** (reranker) → **Tern** (small
answering model) or **Nox** (flagship and agent).

## Why this niche

- Frontier labs build very large models for datacenters. Almost nobody optimizes for **NAS-class
  hardware**: a few GB of RAM, a low-power CPU, often no GPU or only an integrated one.
- The data is **private and multilingual**: contracts, invoices, scans and notes in German, English,
  Swedish and other languages, mixed in one folder tree. Public benchmarks don't test that.
- The models nAI needs are **small and specific**: a multilingual embedding model, a reranker, a 1–4B
  answering model that cites and refuses, and later an agent model for the NAS. These can be trained
  and evaluated by a small team on modest budgets.
- **Distribution is already there**: nAI ships as a container for any NAS and already picks a model to
  fit the hardware (`app/hardware.py`); NithronOS bundles it. A Nithron model can become the default with no
  extra work for the user.

## Principles

These apply to every stage. A pull request that breaks one of them is not merged.

1. **No training on users' data without explicit opt-in.** nAI never sends files, questions or answers
   anywhere for training. Training data is synthetic or public and permissively licensed. If opt-in data
   collection is ever added, it gets its own ADR first.
2. **Check every license before use, and record it.** Every base model, dataset, tool and corpus file
   gets an entry in [MODEL_AND_DATA_LICENSES.md](MODEL_AND_DATA_LICENSES.md) before it is used, the same
   way this repo already avoids AGPL dependencies. No entry, no use.
3. **No training data from services that forbid it.** Training data is never generated with an AI
   service whose terms forbid using its outputs to train competing models. That includes Claude and other
   hosted frontier APIs. Training data is generated with an open-weight model whose license allows it
   (for example Apache-2.0 Qwen models). Every eval and data item has a `provenance` field; anything
   written by Claude is marked (`"author": "claude"`, `"use": "eval-only"`) and kept out of training
   splits.
4. **Every model claim is backed by a nai-bench number.** "Better", "faster" or "multilingual" means a
   row in a committed results file, measured against the previous default on the same nai-bench version.

Working rules that follow from these:

- **No contamination.** Nothing from `evals/nai-bench/` (corpus or questions) is used to generate or
  select training data. Training corpora are generated separately and checked for overlap
  (`training/embed/check_overlap.py`, Stage 1).
- **Pin everything.** Results record the git commit, nai-bench data hashes, model names and settings
  (`evals/run_baseline.py` does this).
- **Licenses we release under:** models and datasets we train are released under a permissive license
  that the base model's license allows (Apache-2.0 by default). nai-bench items we write are CC-BY-4.0 and lab code in `evals/` and `training/` is Apache-2.0, except the
  public-domain statute excerpts, which stay public domain.

## Stages

### Stage 0 – Measurement (in progress)

Deliverables:

- [x] nai-bench v0: 27-file NAS-like corpus (DE/EN/SV/FR/PT; text PDFs, scanned PDFs, photographed
      receipts, DOCX, Markdown, CSV, code, two public-domain statute excerpts) and 56 questions in five
      categories, 11 unanswerable. [`evals/nai-bench/`](../../evals/nai-bench/README.md)
- [x] Retrieval eval on nai-bench (Recall, Precision, Hit, MRR, nDCG, page Hit).
- [x] Answer-quality eval: fact recall, citation hit, unsupported numbers, refusal, language match,
      optional LLM judge with a documented rubric.
- [x] Ollama end-to-end smoke test (`evals/smoke_ollama.sh`), run on 2026-11-22 with qwen2.5:1.5b.
- [x] Baseline with the current defaults: [`evals/results/baseline-2026-11-22.md`](../../evals/results/baseline-2026-11-22.md)
      (hybrid MRR 0.793, Hit@5 0.933; qwen2.5:1.5b answers correct 0.578, correct refusals 0.545), plus a
      reranker variant and a qwen2.5:7b reference (correct 0.822).
- [ ] nai-bench v1: ≥ 300 questions, ≥ 300 files including several hundred distractors, a fixed
      **dev/test split** (test answers not used for any tuning), a second human reviewer for every item.
- [ ] Reference NAS hardware profiles and a latency/RAM benchmark on them (see open questions).

Exit criteria:

- nai-bench v1 is published (CC-BY-4.0) with a test split, and its questions are human-reviewed.
- A baseline on v1 exists for: BM25, current embedding model, hybrid, hybrid + reranker; extractive and
  at least two small LLMs.
- The baseline is reproducible from one command on a clean machine (compose stack + `run_baseline.py`).

### Stage 1 – First models: Nithron Vane 1 and Loupe 1

Plan: [stage1-embedding-finetune.md](stage1-embedding-finetune.md).

Deliverables:

- Synthetic multilingual query–passage pairs generated by an open-weight model from a separately
  generated, NAS-like synthetic corpus (never from nai-bench), with hard negatives.
- **Vane 1** (`nithron/vane-1`): a fine-tune of the current embedding model
  (`paraphrase-multilingual-MiniLM-L12-v2`), exported to ONNX for fastembed, with an int8 variant.
- **Loupe 1** (`nithron/loupe-1`): a cross-encoder trained from Granite R2 97m multilingual (mmBERT-small, once audited, as the
  comparison) on Vane 1's licensed passages with labels from the approved teacher, same export path. Every
  third-party multilingual reranker we checked has MS MARCO in its training data or distilled labels
  (decision 2026-11-26; until Loupe 1, `NAI_RERANKER=auto` stays off).
- A Hugging Face release: model card, license, eval table, data provenance; the training dataset released
  separately.
- nAI options `NAI_EMBEDDINGS_MODEL=nithron/vane-1` and `NAI_RERANKER_MODEL=nithron/loupe-1`; default switch
  only if the exit criteria hold.

Exit criteria (on nai-bench v1 **test** split, embedding-only and hybrid):

- MRR and Hit@5 better than the base model by a margin larger than the bootstrap 95 % interval;
  cross-lingual and table/scan-OCR categories improve; no category drops by more than 0.02.
- Same size class as the base model (≤ ~500 MB ONNX fp32, ≤ ~130 MB int8) and no slower on CPU.
- Licenses of the base model, the generator model and all data recorded and compatible with the release
  license.

### Stage 2 – Answering models: Nithron Tern 1 (and Nox 1)

Deliverables:

- **Tern 1** (`nithron/tern-1`, plus `tern-1-mini` for < 8 GB RAM): a LoRA fine-tune of a 1–4B open model
  (candidates and licenses in the register and in MODEL_NAMING.md) for grounded answers:
  answer only from the passages, cite the file (and page), refuse when the files don't contain the answer,
  answer in the question's language.
- Training data: synthetic (question, passages, grounded answer / refusal) triples generated by an
  open-weight teacher, plus filtered public QA data with compatible licenses.
- **Nox 1** (`nithron/nox-1`, ~8B+): the same training on a larger base for machines with a GPU or lots of
  RAM, as the large tier.
- GGUF exports (Q4_K_M, Q8_0) for Ollama/llama.cpp, and nAI's hardware detection picking Tern or Nox
  (`app/nithron_models.py`).
- nAI prompt changes that make inline citations measurable (today's answers rarely name the file).

Exit criteria (nai-bench answers, test split, same retrieval):

- Beats the best off-the-shelf model of the same size on correct answers and correct refusals, and
  beats the 2026-11-22 baseline (qwen2.5:1.5b: correct 0.578, correct refusal 0.545, language match
  0.709) by a clear margin and closes most of the gap to the qwen2.5:7b reference (correct 0.822,
  correct refusal 0.727); unsupported-number rate does not get worse.
- Runs on the reference NAS CPU profile at a usable speed (target to be set from Stage 0 measurements,
  e.g. first token < 3 s, ≥ 8 tokens/s for a 1.5B Q4 model).

### Stage 3 – NAS agent model (Nithron Nox)

Deliverables:

- One **common NAS tool interface** (`list_shares`, `get_disk_health`, `list_snapshots`, `list_apps`, …;
  see [nas-adapters.md](../architecture/nas-adapters.md)), served as an MCP server by each NAS adapter.
  The NithronOS adapter implements it first; TrueNAS, Unraid and others follow. Read-only tools first.
- nai-agent-bench: tasks with expected tool calls and arguments against **mocked** implementations of the
  common interface (not tied to one NAS), plus per-platform smoke tests.
- A tool-use fine-tune of Nox (and, if it is good enough, Tern); actions that change anything require the
  user's confirmation in the UI and are never executed by the model alone.

Exit criteria:

- Tool-call accuracy on nai-agent-bench above the best same-size open model.
- Zero write actions executed without a confirmation step in the agent-bench and in a red-team set of
  prompt-injection files placed in the indexed shares.

### Stage 4 – Lab practice

- A short technical report with every model release (data, training, evals, limitations).
- Open datasets and models on Hugging Face under the `nithron` organization.
- nAI installs and updates Nithron models automatically on any platform, matched to the hardware (Tern or
  Nox), with a one-click way back to the previous model; NithronOS bundles them.
- A public nai-bench leaderboard file in this repo; external submissions welcome.

## Open questions

1. **Reference hardware.** Which NAS profiles do we measure on? Proposal: Intel N100 (4C, 16 GB), an
   ARM board (RK3588, 8 GB) and a 2-bay entry NAS CPU (e.g. Ryzen V1500B, 8 GB). Do we own them?
2. **nai-bench growth.** Who writes and reviews the next 250+ questions? Claude-written items are allowed
   in eval-only sets (principle 3), but every item should get a human review before it counts as test.
3. **Base embedding model.** Keep `paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0, current default)
   or move to `intfloat/multilingual-e5-small` (MIT) before fine-tuning? Needs a nai-bench v1 comparison.
4. **Teacher model for synthetic data.** Which open-weight model, at which size, on which hardware? See
   the license register for candidates; license and terms must be re-checked at the time of use.
5. **Release license.** Apache-2.0 for models and CC-BY-4.0 or CC0 for datasets? Must stay compatible
   with base-model licenses.
6. **Opt-in data.** Do we ever want opt-in "donate this question" feedback from nAI users? If yes, it
   needs consent UI, anonymization and its own ADR; until then the answer is no.
7. **OCR.** Swedish/French/Portuguese scans need more Tesseract language packs (the image ships `eng+deu`);
   is OCR quality a lab topic (Docling, small VLMs) or out of scope?
8. **Stage 2 compute.** Fine-tuning a 1–4B model fits the local 24 GB GPU with LoRA; is ROCm tooling
   reliable enough, or do we rent NVIDIA time for training runs?
