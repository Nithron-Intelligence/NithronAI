# Stage 1 plan: Nithron Vane 1 and Nithron Loupe 1

> Status: plan, updated 2026-11-23. No training run has been started. Names: [MODEL_NAMING.md](MODEL_NAMING.md). Code: [`training/embed/`](../../training/embed/).
> Part of the [lab roadmap](ROADMAP.md); licenses in the [register](MODEL_AND_DATA_LICENSES.md).

Goals:
- **Nithron Vane 1** (`nithron/vane-1`): a multilingual embedding model, the same size as today's default,
  that retrieves NAS files better in nAI, especially across languages and for OCR'd tables, and ships as an
  ONNX model that fastembed loads. Sections 1–9 below are about Vane 1.
- **Nithron Loupe 1** (`nithron/loupe-1`): a multilingual reranker that fits a NAS CPU; section 11.

## Starting point (nai-bench v0 baseline, 2026-11-22)

From [`evals/results/baseline-2026-11-22.md`](../../evals/results/baseline-2026-11-22.md), 45 answerable
questions:

| Retrieval | MRR | Hit@1 | Hit@5 | Page Hit@5 |
|---|---|---|---|---|
| BM25 | 0.671 | 0.556 | 0.800 | 0.636 |
| embedding (current model) | 0.753 | 0.644 | 0.911 | 0.864 |
| hybrid | 0.793 | 0.667 | 0.933 | 0.773 |
| hybrid + default reranker | 0.791 | 0.689 | 0.956 | 0.727 |

The weak spots are cross-language questions (hybrid MRR 0.650 when the question's language differs from the
file's, against 0.858 in the same language) and table/scan-OCR questions (MRR 0.610). With 45 questions the
95 % interval on MRR is roughly ±0.1 (an estimate, not a computed bootstrap), so **nai-bench v1 (≥ 300 questions, test split) is a prerequisite
for any release claim** (principle 4).

## 1. Base model (Vane 1)

| | `paraphrase-multilingual-MiniLM-L12-v2` (**chosen**, 2026-11-23) | `multilingual-e5-small` (comparison candidate) |
|---|---|---|
| License | Apache-2.0 | MIT |
| Size | 118M params, 384-d, 470 MB ONNX fp32 / 118 MB int8 (measured) | 118M params, 384-d, similar |
| In nAI today | yes, the default; all existing indexes use it | no (needs `query:`/`passage:` prefixes in nAI) |
| Max length | 128 tokens trained (we use 256) | 512 |

**Decision (2026-11-23):** Vane 1 is a fine-tune of `paraphrase-multilingual-MiniLM-L12-v2`. Users get a
drop-in upgrade (same dimension, same pooling, re-embedding only), and the comparison on nai-bench is clean.
`multilingual-e5-small` (MIT) goes through the same pipeline as the comparison candidate; if it wins clearly
on the v1 test split, that becomes Vane 1.5 or Vane 2 (a different base is a major version). Not chosen: `bge-m3` (MIT, 568M,
too slow for NAS CPUs; useful as a reference and for mining).

Both model licenses allow releasing a fine-tune under Apache-2.0 with attribution, and neither restricts
naming (see MODEL_NAMING.md).

**Open item: audit the base models' training data.** The model licenses are clear, but what
`paraphrase-multilingual-MiniLM-L12-v2` (and e5-small) were trained on has not been checked: which datasets,
under which terms (e.g. any non-commercial data such as MS MARCO), and whether that affects a commercial
release. To do before the Vane 1 release: list the training datasets from the model cards and papers,
record their licenses in the register, and note the result in the model card.

## 2. Training corpus (never nai-bench)

1. **Synthetic NAS corpus.** An open-weight teacher (approved list in the register) writes fictional
   documents of the kinds nAI sees: contracts, invoices, statements, manuals, meeting notes, letters,
   receipts, spreadsheets, code and config files, in DE/EN/SV/FR/PT and more. Variety comes from a seed
   list of document types × countries × topics; each document gets a provenance header. Scans are rendered
   with the nai-bench renderer (`evals/nai-bench/build_corpus.py` functions), then **OCR'd by nAI's own
   extractor**, so training sees real OCR noise.
2. **Public, permissive text.** Public-domain statutes (DE, SE, EU), government forms and manuals,
   permissively licensed documentation. Each source gets a register row first. Not the statute sections
   that are in nai-bench (BGB §§ 535, 551, 573c; Jordabalken 12:4): the overlap check flags them by design.
3. `make_passages.py` chunks everything exactly as nAI does (same extractor, same `chunk_sections`, same
   `"<context header>\n<text>"` input), records license, source and **author** (required; Claude, GPT and
   other hosted-API authors are refused), and detects each passage's language (en/de/sv/fr/pt only; other
   languages get no label and skip the language check, so add them to the detector before using them).

Target size: 30–50k passages, 100–150k pairs.

## 3. Synthetic queries (principle 3)

`generate_pairs.py` asks the teacher, per passage, for 3–4 queries: one or two in the passage's language,
the rest in other languages (cross-lingual), at least one keyword-style. Rules in the prompt: answerable
from the passage alone, no long copied phrases, no invented facts.

- **Teacher:** `qwen2.5:7b` (Apache-2.0) for the first run; `qwen3:14b` / `mistral-small3.1` (Apache-2.0)
  if quality is too low. Hosted APIs (Claude, GPT, …) are refused by code (`common.APPROVED_TEACHERS`).
- **Provenance on every pair:** `author` (the teacher) and its license, prompt version, date, `passage_author`,
  passage license and source, `use: training`, the same `author`/`use` keys as nai-bench items. `train.py`
  refuses pairs without `use: training` or with a forbidden author or passage author.
- **Robustness:** each passage is retried 3 times and skipped on failure; `--resume` appends to the output
  and skips finished passages; `--limit` takes a seeded random sample, so a pilot covers all files.
- **Filters:** length bounds, de-duplication, query must not appear verbatim in the passage, and the
  query's detected language must match its label. The smoke run on 2026-11-22 showed why: `qwen2.5:7b`
  labelled English keyword queries as Portuguese and made Swedish typos ("Uppsattningsperioden").
- **To add before the real run:** a round-trip consistency filter. Keep a pair only if the base model
  ranks its passage in the top 20 for the query among all passages; this drops vague or wrong queries.
  Also a 200-pair human spot check per language.
- **Contamination check:** `check_overlap.py` compares 8-gram shingles of every passage and query with
  nai-bench and fails on > 10 % overlap or a repeated nai-bench question (verified to catch both).

## 4. Hard negatives

`train.py` mines one or two negatives per pair with the base model (`mine_hard_negatives`): skip the top
5 ranks (often unlabeled positives, e.g. the 2023 vs 2024 version of the same invoice), sample from ranks
5–50, and require a 5 % relative margin below the positive. Same-document chunks are the main false-negative
risk; a later step should exclude negatives from the positive's own file.

## 5. Loss and training settings

- **Loss:** `MultipleNegativesRankingLoss` (in-batch negatives + mined negatives); `CachedMultipleNegatives
  RankingLoss` (`--cached-loss`) for batches of 256–1024 on limited memory.
- **Batch sampler:** `NO_DUPLICATES` (duplicate texts in a batch would be false negatives).
- **Settings (first run):** 1 epoch, lr 2e-5, warmup 10 %, batch 64 (128–256 with the cached loss),
  max length 256, bf16 on GPU, seed 13. Evaluate every 500 steps on held-out passages.
- **Held-out split:** 5 % of passages (all their pairs) never seen in training; identical texts are merged
  into one passage id first so they can't leak across the split. The eval corpus is the held-out passages
  plus 2000 random train passages as distractors (`--eval-distractors`); IR metrics before and after.
- Overfitting guard: compare with the base model on nai-bench v1 *dev* after training; stop if same-language
  lookup drops.

## 6. Export for fastembed

`train.py` saves the model, exports `onnx/model.onnx` and `onnx/model_quint8_avx2.onnx`, and checks that
**fastembed** (what nAI runs) produces the same vectors as PyTorch (min cosine ≥ 0.99). Verified on
2026-11-22 with the base model: min cosine 1.0000, fp32 470 MB, int8 118 MB.

nAI change needed (small, Stage 1 deliverable): register the model with
`TextEmbedding.add_custom_model(model="nithron/vane-1", pooling=MEAN, normalization=True,
sources=ModelSource(hf="nithron/vane-1"), dim=384, model_file="onnx/model.onnx")` before
loading, behind `NAI_EMBEDDINGS_MODEL`. Switching models already triggers a re-embed.

## 7. Evaluation on nai-bench

1. Build the bench stack with `NAI_EMBEDDINGS_MODEL=nithron/vane-1` (or a local path).
2. `python evals/run_baseline.py --reviewed-only --label vane-1-rc1 --methods bm25,embedding,hybrid`, and the
   same with the reranker on. Training runs record the target with `train.py --release vane-1-rc1`.
3. Compare with the baseline on the v1 **test** split: overall MRR / Hit@5 / page Hit@5, by category, and by
   the derived cross-lingual flag; paired bootstrap 95 % intervals over questions.
4. Also report: CPU latency per query and per 1000 passages on the reference NAS profiles, ONNX size,
   peak RAM.

Release bar (from the roadmap): better MRR and Hit@5 than the base model beyond the bootstrap interval,
cross-lingual and table/scan-OCR improve, no category drops by more than 0.02, same size class, no slower.

## 8. Hugging Face release checklist

- [ ] Model card: intended use (retrieval over private files with nAI), languages, limits, training data
      description, evaluation table **with links to the committed nai-bench result files**, base model,
      teacher model.
- [ ] License: Apache-2.0 (compatible with the base model's Apache-2.0/MIT); `LICENSE` file in the repo.
- [ ] Data provenance: teacher model + license, prompt version, corpus sources and licenses, the
      contamination check output, "no user data" statement (principle 1).
- [ ] Files: PyTorch weights, `onnx/model.onnx`, `onnx/model_quint8_avx2.onnx`, tokenizer, fastembed snippet.
- [ ] The training pairs as a separate dataset (CC-BY-4.0 or CC0), with the same provenance fields.
- [ ] Technical note (short): data, settings, results, failure cases.
- [ ] nAI PR: custom-model registration + docs; `app/nithron_models.py` status `released`.
- [ ] Training-data audit of the base model done and in the model card (section 1).

## 9. Hardware and cost

Measured on this workstation (2026-11-22):

| | |
|---|---|
| CPU | AMD Ryzen 9 7950X, 16 cores / 32 threads |
| RAM | 30 GiB (+ swap) |
| GPU | AMD Radeon RX 7900 XTX, **24 GiB VRAM** (gfx1100; ROCm works in Docker: Ollama 0.40.17-rocm used it for the baseline) |
| Disk | 494 GB free on `/mnt/vault` |
| CPU encode speed (base model, 110-token passages, 16 threads) | 187 passages/s |

**Verdict: Stage 1 runs locally; no rented GPU needed.**

- *Teacher generation (extrapolated from a 3-passage smoke run):* `qwen2.5:7b` on the 7900 XTX took about
  0.7 s per passage (one call returning 3–4 queries). 40k passages ≈ 8 h sequential, an estimated 2–3 h with
  4 parallel requests (`OLLAMA_NUM_PARALLEL=4`). A 14B teacher is roughly twice as slow (estimate).
- *Training (estimates; only the CPU encode speed was measured):* a 118M-parameter model with MNRL. On the
  GPU (PyTorch ROCm wheels; the device nodes are accessible) we expect well under an hour per epoch for 150k
  pairs. Even CPU-only looks feasible: from the measured 187 passages/s forward, a forward+backward over 3
  texts per pair suggests roughly 15–25 pairs/s,
  i.e. 2–3 h per epoch.
- *Cost (estimate):* ~10 GPU-hours at ~350 W ≈ 3.5 kWh, about €1–2 of electricity.
- *If renting instead* (rough on-demand prices, check before booking): a single A100 80 GB or H100 runs
  the whole Stage 1 (vLLM generation + training + export) in ~4–6 h, about $10–20.
- *Stage 2 outlook:* LoRA on a 1–4B model in bf16 fits 24 GB with gradient checkpointing; ROCm tooling
  (bitsandbytes/QLoRA, flash-attention) is less mature than CUDA, so budget ~$50–150 of rented H100 time
  as a fallback.

## 11. Loupe 1 (reranker)

Comparison of permissive multilingual rerankers on nai-bench v0
([`evals/results/rerankers-2026-11-23.md`](../../evals/results/rerankers-2026-11-23.md)), each re-scoring
nAI's top-30 hybrid candidates on 2 CPU threads:

| Reranker | License | Params | MRR | MRR cross-lingual | Median s / question | Verdict |
|---|---|---|---|---|---|---|
| none (hybrid order) | – | – | 0.793 | 0.650 | – | today's default |
| ms-marco-MiniLM-L-6 (old default) | Apache-2.0 | 22M | 0.791 | 0.483 | 0.67 | English-only: hurts cross-lingual; off by default now |
| mmarco-mMiniLMv2-L12 | Apache-2.0 (data: translated MS MARCO, non-commercial) | 118M | 0.802 | 0.714 | 0.90 | small gain, data-lineage risk |
| **bge-reranker-v2-m3 (int8)** | **Apache-2.0** | 568M | **0.918** | **0.917** | 3.7 (top-30), **2.1 (top-10)** | **Loupe 1 base** |
| Qwen3-Reranker-0.6B | Apache-2.0 | 596M | 0.956 | 1.000 | 40 | best quality, ~10× too slow for a NAS: **teacher** |
| gte-multilingual-reranker-base | Apache-2.0 | 306M | – | – | – | not run: needs `trust_remote_code`, no ONNX build |

**Decision (proposed): Loupe 1 = a fine-tune of `BAAI/bge-reranker-v2-m3`**, shipped as int8 ONNX for
fastembed (fastembed already supports this model, so nAI needs no new runtime).

- Why: the only candidate that is permissive, multilingual, runnable without remote code, and inside a NAS
  CPU budget, and it already gives +0.125 MRR (+0.27 cross-lingual) out of the box. Even reranking only the
  top 10 keeps most of the gain (MRR 0.878) at ~2 s per question on 2 fast cores.
- Distillation: Qwen3-Reranker-0.6B (Apache-2.0) scores best (0.956) but is far too slow for a NAS; use it
  as the **teacher** that labels (query, passage) pairs from the synthetic corpus (scores, not text, so the
  same open-weight teacher rules apply), and train Loupe 1 to match it.
- Budget target for Loupe 1: top-10 candidates in ≤ 2 s on a 4-core NAS CPU, ≤ 1 GB RAM. If bge-m3 int8 stays
  too slow on real NAS hardware (to be measured), distill into a smaller XLM-R/MiniLM student as Loupe 1 mini.
- Until Loupe 1 ships: nAI keeps reranking off by default; admins with capable hardware can set
  `NAI_RERANKER=true` and `NAI_RERANKER_MODEL=BAAI/bge-reranker-v2-m3-int8`.
- Same open items as Vane: training-data audit of the base, release checklist (section 8), nai-bench v1.

## 10. Order of work

1. nai-bench v1 (dev/test split, human review), *before* any model claim.
2. Synthetic corpus generator (teacher prompts per document type) and a 1k-passage pilot; spot-check.
3. Consistency filter; pilot training run (1k pairs) to check the loop end to end on the GPU.
4. Full data generation; contamination check; training; export; nai-bench v1 eval.
5. Release checklist; nAI custom-model support; NithronOS tier mapping.
