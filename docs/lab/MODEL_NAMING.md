# Nithron model names

> Status: accepted 2026-11-23. Names and IDs are defined in one place in code:
> [`apps/nai-core/app/nithron_models.py`](../../apps/nai-core/app/nithron_models.py). Rename there, then update
> this page.

Nithron models get a **family name per role**, plus a **version number**: "Nithron Vane 1", then
"Nithron Vane 1.5", "Nithron Vane 2". The pipeline inside nAI is **Vane → Loupe → Tern or Nox**.

## The four families

| Name | Meaning | Role | Talks to users? | Target size | Runs on | Stage |
|---|---|---|---|---|---|---|
| **Vane** | A weather vane points a direction; vectors are direction and magnitude. | Embedding model: turns chunks and questions into vectors for semantic and cross-language search | No | ~100–500M | Any NAS CPU | Stage 1 |
| **Loupe** | A jeweller's lens for inspecting fine detail. | Reranker: re-scores the top search hits so the best ones come first (multilingual) | No | ~100–600M | Any NAS CPU | Stage 1–2 |
| **Tern** | A seabird that travels the farthest on the least energy. | Small answering model: grounded, cited answers; refuses when the files don't contain the answer | Yes | ~1–4B | CPU-only or low-RAM NAS | Stage 2 |
| **Nox** | Latin for night: the flagship that guides you through the dark, like navigating by night. | Flagship: stronger answers for hard questions and long documents, plus agent and tool use | Yes | ~8B+ | NAS or PC with a GPU or lots of RAM | Stage 2 (large tier) and Stage 3 |

## Rules

1. **One syllable.** Every family name is one syllable (Vane, Loupe, Tern, Nox). Any future family follows
   the same rule.
2. **Always branded in public.** Full public names always carry the brand: "Nithron Vane 1",
   "Nithron Nox 1". Never "Nox" alone in marketing, release notes, or model cards: other products use these
   words. Inside nAI's own UI, where the brand is obvious, the short form ("Tern 1") is fine.
3. **IDs.** Hugging Face: `nithron/<family>-<version>[-<variant>]`, all lower case: `nithron/vane-1`,
   `nithron/loupe-1`, `nithron/tern-1`, `nithron/nox-1`, `nithron/tern-1-mini`. Ollama: the same name
   (`nithron/tern-1-mini:q4_K_M`). `nithron_models.parse_model_id` understands both.
4. **First versions:** Vane 1 (base: `paraphrase-multilingual-MiniLM-L12-v2`), Loupe 1 (base: the winner of
   the reranker comparison, see the Stage 1 plan), Tern 1, Nox 1 (bases chosen in Stage 2).

## Versions

> **Accepted 2026-11-23:** `.5` minor steps, `-mini`/`-max` size variants, and any Vane change forces a
> re-index. These rules are tied to code: `app/nithron_models.py` (IDs, variants) and nAI's
> embedding-model change detection (`EmbeddingService.reindex_required`).

| Change | Example | When |
|---|---|---|
| **Major** (`1` → `2`) | Vane 2 | New base model or architecture, a new tokenizer, a changed output format (e.g. a different embedding dimension, a new prompt/chat format, a new tool-call schema), or training from scratch on a new data generation. Users may need to re-index (Vane) or update prompts (Tern/Nox). |
| **Minor** (`1` → `1.5`) | Tern 1.5 | Same base and interface, clearly better on nai-bench (new data, more training, better alignment). Drop-in replacement. We use `.5` steps for named minor releases, like "1.5"; there is no "1.1". |
| **Fix** (no new name; **not for Vane**) | `nithron/tern-1`, revision `2027-03-02` | Bug fixes, re-exports, quantization fixes with no meaningful score change. Published as a new Hugging Face revision of the same ID and listed in the model card's changelog. Vane never gets same-name fixes (see below). |

Notes:
- **Every Vane version change means re-embedding**, even a minor one, because vectors from different
  weights aren't comparable. nAI detects a change **by the model ID**: stored vectors carry the ID they were
  made with, and when it differs from the configured model nAI pauses semantic search and asks the admin
  before re-indexing (`NAI_EMBEDDINGS_AUTO_REINDEX=true` re-embeds without asking).
- **Vane weights are never replaced in place under the same name.** Any change to Vane weights, even a
  "fix", ships under a new ID (Vane 1 → Vane 1.5), never as a new revision of `nithron/vane-1`: a silent
  weight swap under the same ID would go undetected and mix incompatible vectors. (Fix revisions are fine
  for Loupe, Tern and Nox, whose outputs aren't stored.)
- A version number goes up only with a committed nai-bench result that backs the release (principle 4).
- Versions are per family: Vane 2 can ship while Tern is still at 1.

## Size variants

Within a family and version, size variants get a suffix:

| Suffix | Meaning | Example |
|---|---|---|
| `-mini` | Smaller than the standard size of that family (for the weakest hardware) | `nithron/tern-1-mini` (e.g. ~1B), "Nithron Tern 1 mini" |
| *(none)* | Standard size | `nithron/tern-1` (e.g. ~3–4B) |
| `-max` | Larger than standard (more quality, more hardware) | `nithron/nox-1-max` |

Rules: at most these two suffixes; a variant shares the version's training data and interface; a family
whose sizes would overlap the next family's target size gets a new family instead (a 10B "Tern max" would
be a Nox). Quantizations (Q4, Q8, int8 ONNX) are file variants inside one model ID, not names.

## In nAI

- **Model picker** (Settings → Models): shows the display name without the brand ("Tern 1 mini"), the role,
  the size, and a "recommended for this machine" badge. Third-party models stay listed by their own names.
- **Hardware detection** (`app/hardware.py` → `nithron_answering_model`, from `nithron_models`): Nox when the
  machine has a GPU with at least 10 GB of VRAM, or at least 32 GB of RAM and 8 cores; otherwise Tern, and
  Tern mini below 8 GB of RAM. `/system` reports the choice (`nithron_model`) with its status (`planned`
  until released). Vane and Loupe have one size each for now and run everywhere.
- **Settings:** `NAI_EMBEDDINGS_MODEL=nithron/vane-1`, `NAI_RERANKER_MODEL=nithron/loupe-1`,
  `NAI_LLM_MODEL=ollama/nithron/tern-1`.

## In nai-bench results

- Run labels use the model ID slug and a release-candidate suffix while testing: `vane-1-rc1`,
  `loupe-1-rc2`; the final run is labelled with the slug (`vane-1`).
- `evals/run_baseline.py` records every Nithron model it detects in the server config under
  `meta.nithron_models` (ID, display name, role), and the Markdown summary names them in full
  ("Nithron Vane 1"). Third-party models are recorded by their own IDs.

## Base models: what their licenses say about names and attribution

Prefer Apache-2.0 or MIT bases. For both, a fine-tune may get our own name; the model card names the
base model, keeps its copyright/license notice, and says what we changed.

| Tier | Candidate base | License | Naming rule | Attribution |
|---|---|---|---|---|
| Vane | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (**chosen for Vane 1**) | Apache-2.0 | None; may not imply endorsement | Keep license + NOTICE; state changes |
| Vane | `intfloat/multilingual-e5-small` (comparison) | MIT | None | Keep copyright + license notice |
| Loupe | `BAAI/bge-reranker-v2-m3` | Apache-2.0 | None | Keep license; state changes |
| Loupe | `Alibaba-NLP/gte-multilingual-reranker-base` | Apache-2.0 | None | Keep license; state changes |
| Loupe | `Qwen/Qwen3-Reranker-0.6B` | Apache-2.0 | None | Keep license; state changes |
| Loupe | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Apache-2.0 (model); training data mMARCO is derived from MS MARCO (non-commercial terms) | None | As Apache-2.0; data lineage risk |
| Tern | `Qwen/Qwen3-1.7B`, `Qwen/Qwen3-4B`, `Qwen/Qwen2.5-1.5B-Instruct` | Apache-2.0 | None | Keep license; state changes |
| Tern | `HuggingFaceTB/SmolLM3-3B` | Apache-2.0 | None | Keep license; state changes |
| Tern | `microsoft/Phi-4-mini-instruct` | MIT | None | Keep copyright + license notice |
| Tern | `Qwen/Qwen2.5-3B-Instruct` | Qwen Research License | Non-commercial | **Avoid** |
| Nox | `Qwen/Qwen3-8B`, `Qwen/Qwen3-14B` | Apache-2.0 | None | Keep license; state changes |
| Nox | `allenai/OLMo-2-1124-7B-Instruct`, `allenai/OLMo-2-0325-32B-Instruct` | Apache-2.0 | None | Keep license; AI2 also publishes the training data, a good fit for an open lab |
| Nox | `ibm-granite/granite-3.3-8b-instruct` | Apache-2.0 | None | Keep license; state changes |
| Nox | `mistralai/Ministral-8B-Instruct-2410` | Mistral Research License | Research only | **Avoid** |
| any | `google/gemma-3-*` | Gemma Terms of Use | Derivatives must carry the Gemma terms and use restrictions | **Avoid** |
| any | `meta-llama/Llama-3.x-*` | Llama Community License | Derivative names must start with "Llama"; "Built with Llama" display required | **Avoid** (conflicts with our naming) |

Licenses were read from the Hugging Face model metadata on 2026-11-22/23 and are also in the
[license register](MODEL_AND_DATA_LICENSES.md); re-check before training.

## Name clashes and open questions

Already checked (web, before adoption):
- **Rejected for clashes:** Glint (Glint Research models; a Rust AI framework), Flint (Recursive's
  open-weight model, in Ollama's library), Glimmer / Ember / Spark (Meta's Muse models), Kryon, Vexor.
- **Known non-AI or hobby overlaps** (acceptable with the brand): Nox (NoxPlayer, an Android emulator;
  `nox`, a Python test runner; a hobby model "Nox-Alpha"), Loupe (GNOME's image viewer), Tern (a small hobby
  research model "Tern-1").

Open:
- **Name review** for "Nithron Vane", "Nithron Loupe", "Nithron Tern" and "Nithron Nox" (EUIPO,
  DPMA, USPTO, classes 9 and 42) before the first public release.
- Whether to register the family names as marks together with "Nithron".
