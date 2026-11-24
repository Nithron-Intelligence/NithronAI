# Reranker training-data audit (round 9)

> Audit of the reranker nAI ships (`BAAI/bge-reranker-v2-m3`, int8 ONNX), the planned Loupe 1 teacher
> (`Qwen/Qwen3-Reranker-0.6B`) and the multilingual alternatives we could find. Written 2026-11-24, same method as
> the [embedding audit](vane1-base-model-audit.md): model cards, papers and dataset pages, each claim with its
> source. Not legal advice. The bar is the one from the data rules: no **non-commercial** data in a model's stated
> lineage; upstream CC-BY-SA is accepted and recorded for lawyer review (decision 2026-11-23).

## Verdicts

| Model | Weights | Verdict | Why |
|---|---|---|---|
| `BAAI/bge-reranker-v2-m3` (nAI's reranker since 0.6.0) | Apache-2.0 | **fails the clean-data bar → the human decides** | MS MARCO (non-commercial) is in its base model's fine-tuning data and in the data bundle the reranker itself was trained on. |
| `onnx-community/bge-reranker-v2-m3-ONNX` (where fastembed gets the int8 file) | no license stated | **low risk, unverifiable provenance** | Automatic conversion of the Apache-2.0 weights; the repo states no license and no checksum of the source. |
| `Qwen/Qwen3-Reranker-0.6B` (Loupe 1's planned teacher) | Apache-2.0 | **fails the clean-data bar → the human decides** | Qwen's report lists MS MARCO among the labeled data of the supervised stage, which is the only stage the reranker goes through. |
| `Horizon-Labs/multilingual-reranker-small` / `-base` (alternative) | Apache-2.0 | **clean data, tainted labels** (closest we found) | Every listed dataset is permissive, but the labels are distilled from `Qwen3-Reranker-4B`, which has the same lineage as the 0.6B. |

No multilingual reranker we found is clean end to end with a published training-data statement. IBM's
`granite-embedding-reranker-english-r2` is (it excludes MS MARCO explicitly) but it is English-only.

## bge-reranker-v2-m3

- **Card:** `license: apache-2.0`; model list gives base model `bge-m3`, "Multilingual"
  ([card](https://huggingface.co/BAAI/bge-reranker-v2-m3)).
- **Its own fine-tuning data:** "we train it on a mixture of multilingual datasets: bge-m3-data, quora train data,
  fever train data" ([card](https://huggingface.co/BAAI/bge-reranker-v2-m3), same text in the
  [FlagEmbedding llm_reranker README](https://github.com/FlagOpen/FlagEmbedding/blob/master/research/llm_reranker/README.md)).
  The sentence opens with the LLM rerankers' initialisations (gemma-2b, MiniCPM), so strictly it may describe those;
  BAAI publishes no separate list for v2-m3. Either way the base model carries the same data (next point).
- **Base model bge-m3:** paper §3.1: "For English, we incorporate 8 datasets, including HotpotQA, TriviaQA, NQ,
  MS MARCO, COLIEE, PubMedQA, SQuAD, and NLI data from SimCSE"; Chinese adds DuReader, **mMARCO-ZH**, T2-Ranking,
  LawGPT, CMedQAv2, NLI-zh, LeCaRDv2; other languages Mr. TyDi and MIRACL; plus GPT-3.5-generated MultiLongDoc
  ([arXiv 2402.03216](https://arxiv.org/html/2402.03216)). The bundle
  [`Shitao/bge-m3-data`](https://huggingface.co/datasets/Shitao/bge-m3-data) ("all the fine-tuning data for the
  bge-m3 model") lists MS MARCO and mMARCO-zh and states no license.
- **Terms of the flagged datasets:**
  - MS MARCO: "intended for non-commercial research purposes only" ([microsoft.github.io/msmarco](https://microsoft.github.io/msmarco/),
    verified in the embedding audit). **Non-commercial.**
  - mMARCO (translations of MS MARCO): released "under Apache license 2.0"
    ([HF card](https://huggingface.co/datasets/unicamp-dl/mmarco)); it does not say whether MS MARCO's terms carry
    over. A translation of non-commercial text is still derived from it; we treat it like MS MARCO.
  - Quora question pairs: the release page refused automated access (HTTP 403) and mirrors state no terms;
    **unverified** (Quora's release is commonly described as non-commercial; check by hand).
  - FEVER: annotations "incorporate material from Wikipedia" and are under the Wikipedia article terms, "or …
    Creative Commons Attribution-ShareAlike License (version 3.0)" ([FEVER license](https://fever.ai/download/fever/license.html)).
    Upstream CC-BY-SA: accepted by decision 2, recorded for the lawyer.
- **Also noted:** the maintainers say there was "no training data for cross-lingual reranking task" when training it
  ([discussion #6](https://huggingface.co/BAAI/bge-reranker-v2-m3/discussions/6)), which fits its weak
  cross-language numbers on nai-bench.

**Verdict:** the same situation as MiniLM in the embedding audit: Apache-2.0 weights, non-commercial data in the
stated lineage. Whether data terms bind trained weights is legally unsettled, so this does not prove a
violation; it fails our clean-data bar and is the human's risk decision.

## The int8 ONNX file nAI downloads

fastembed's registry entry `BAAI/bge-reranker-v2-m3-int8` points at `onnx-community/bge-reranker-v2-m3-ONNX`,
file `onnx/model_int8.onnx` (0.57 GB), and declares `license="apache-2.0"`
([fastembed source](https://github.com/qdrant/fastembed/blob/main/fastembed/rerank/cross_encoder/onnx_text_cross_encoder.py)).
The repo's card has no `license:` field and no license file; it says "This is an ONNX version of
BAAI/bge-reranker-v2-m3. It was automatically converted and uploaded using [a conversion space]"
([card](https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX)). A conversion cannot relicense the
weights, so they stay Apache-2.0 (the NOTICE/attribution duty is ours when we redistribute; nAI only downloads).
The gap is provenance, not license: nothing ties the int8 file to BAAI's checkpoint. Loupe 1 was already planned
to ship our own export with checksums; that covers it.

## Qwen3-Reranker-0.6B

- **Card:** `license: apache-2.0`, base `Qwen/Qwen3-0.6B-Base`, no dataset list; loads with standard transformers
  (no `trust_remote_code`) ([card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)).
- **Training:** "the reranking model's training process does not include a first-stage weakly supervised training
  phase" (report §3.2); blog: "For the Reranking model … we directly employed high-quality labeled data for
  supervised training" ([blog](https://qwenlm.github.io/blog/qwen3-embedding)).
- **The labeled data:** report Table 6 (Appendix A.1), supervised fine-tuning: "MS MARCO, NQ, HotpotQA, NLI,
  Dureader, T2-Ranking, SimCLUE, MIRACL, MLDR, Mr.TyDi, Multi-CPR, CodeSearchNet .etc" (~7M labeled pairs) plus
  ~12M synthetic pairs from Qwen3-32B ([arXiv 2506.05176](https://arxiv.org/html/2506.05176v3)). The report does
  not give a reranker-only subset, and nothing says MS MARCO was left out for it.
- `Qwen3-Reranker-4B` has the same card text and no data list ([card](https://huggingface.co/Qwen/Qwen3-Reranker-4B)).
  Both cards also call the series "proprietary" in prose while declaring Apache-2.0 in the metadata (to note for
  the lawyer).

**Verdict:** fails the clean-data bar (non-commercial MS MARCO among the only training stage's data). Using it as a
teacher means its scores become Loupe 1's labels, which carries the lineage one step further (as below).

## Alternatives we looked for

Criteria: multilingual (at least de, en, es, fr, pt), Apache-2.0/MIT, published training-data statement with no
non-commercial data, no `trust_remote_code`, ONNX on CPU.

| Candidate | License | Result |
|---|---|---|
| `Horizon-Labs/multilingual-reranker-small` (141M, mmBERT-small) | Apache-2.0 | Data: FineWeb-2/FineWeb (ODC-BY), MIRACL train (Apache-2.0), WebFAQ (CC-BY-4.0), synthetic queries from an Apache-2.0 LLM; "distilled from Qwen3-Reranker-4B"; int8 ONNX 268 MB ([card](https://huggingface.co/Horizon-Labs/multilingual-reranker-small)). **Tested below.** |
| `Horizon-Labs/multilingual-reranker-base` (308M, mmBERT-base) | Apache-2.0 | Same data (without WebFAQ) and teacher; int8 ONNX 641 MB ([card](https://huggingface.co/Horizon-Labs/multilingual-reranker-base)). **Tested below.** |
| `syntriq/lupe-multilingual-reranker-base` (308M) | Apache-2.0 | Starts from Horizon base; adds 7M English pairs from `cross-encoder/ettin-reranker-v1-data` "MS MARCO parts removed" (that dataset does contain MS MARCO configs and labels from `mxbai-rerank-large-v2`, whose data is undocumented); teacher not named; one-person publisher; name close to our "Loupe" ([card](https://huggingface.co/syntriq/lupe-multilingual-reranker-base)). Not tested. |
| `ibm-granite/granite-embedding-reranker-english-r2` | Apache-2.0 | Clean ("we do not use the popular MS-MARCO retrieval dataset … due to its non-commercial license") but **English only** ([card](https://huggingface.co/ibm-granite/granite-embedding-reranker-english-r2)). No multilingual Granite reranker exists. |
| `mixedbread-ai/mxbai-rerank-base-v2` | Apache-2.0 | No training-data statement ("technical report is coming soon"). |
| `Alibaba-NLP/gte-multilingual-reranker-base` | Apache-2.0 | No data statement on the card; needs `trust_remote_code` before transformers 5.18. |
| `jinaai/jina-reranker-v2-base-multilingual` | CC-BY-NC-4.0 | Non-commercial. |

The Horizon models' own data is clean, and `mmBERT-base` (MIT; pre-training on FineWeb2, DCLM, MegaWika,
StackExchange, arXiv …, [card](https://huggingface.co/jhu-clsp/mmBERT-base)) has upstream CC-BY-SA only. Their only
problem is that a teacher with MS MARCO in its lineage produced the labels. That is weaker than training on MS
MARCO directly, but it is the same kind of question Loupe 1's plan already raises.

## Measured on nai-bench v1 dev (PROVISIONAL)

Offline, same setup as nAI with the reranker on: nAI 0.7.0 (Granite R2 97m, reranker off) gives its hybrid
top-30 for the 47 answerable v1 dev questions, and each model re-scores the **top 10** (like
`NAI_RERANKER_CANDIDATES=10`) on **8 CPU threads** (Ryzen 9 7950X, inside the trainer container, GPU hidden).
Result files: [`v1-dev-rerankers-r9-2026-11-24.md`](../../evals/results/v1-dev-rerankers-r9-2026-11-24.md) / `.json`;
script `evals/rerankers/bench_rerankers.py run --bench evals/nai-bench/v1/questions-dev.jsonl --rerank-top 10
--threads 8`.

| Reranker | Lineage verdict | MRR | Hit@1 | MRR cross-language (n = 14) | Median s / question | p90 s |
|---|---|---|---|---|---|---|
| none (hybrid order) | – | 0.834 | 0.766 | 0.599 | – | – |
| bge-reranker-v2-m3 int8 (shipped) | fails | 0.896 | 0.872 | 0.652 | 0.81 | 1.00 |
| Horizon multilingual-reranker-small int8 | clean data, distilled labels | 0.886 | 0.851 | 0.616 | **0.42** | 0.60 |
| Horizon multilingual-reranker-base int8 | clean data, distilled labels | **0.905** | **0.894** | **0.682** | 0.98 | 1.36 |
| Qwen3-Reranker-0.6B (reference) | fails | 0.896 | 0.872 | 0.652 | 17.6 | 18.4 |

- The "none" row reproduces nAI's own hybrid run with Granite (MRR 0.834), so the candidates are the right ones.
- Hit@5 is 0.915 for every row (cross-language 0.714): no reranker moved a missed gold file into the top 5.
  Fusion's cross-language losses have to be fixed before reranking (fusion weights, queued).
- **PROVISIONAL and small:** 47 questions, no item reviewed; the 95 % margin on MRR is about ±0.09, so the three
  encoder rerankers are statistically tied. What the numbers do show: Horizon-small reaches the same quality at
  half bge's latency and a quarter of its parameters; Horizon-base is level with bge at similar latency.
- Peak RAM in the result file is the worker process, which loads PyTorch for the sentence-transformers ONNX path;
  it is not comparable with fastembed's footprint in nAI and is left out here.
- Qwen3's latency is with PyTorch on all cores (it ignored the 8-thread cap in part); it is only a reference.
- No default was changed. Running a Horizon model inside nAI would need a custom-model registration for
  fastembed's cross-encoder (ModernBERT ONNX, no `token_type_ids`); not done.

## What a failed audit means

See "Waiting on the human" in [HANDOFF.md](../HANDOFF.md). In short:

- **Shipped auto-enable (0.6.0, 0.7.0):** on 8+ core boxes nAI downloads and runs a reranker whose lineage fails
  the bar. Options: accept and record it for the lawyer (as with MiniLM until 0.7.0), make `auto` resolve to off in
  the next release until a clean reranker exists, or switch to a cleaner model. No default was changed.
- **Loupe 1:** both its planned base (bge-reranker-v2-m3) and its teacher (Qwen3-Reranker-0.6B) fail. A clean
  route is a cross-encoder trained from a clean encoder (Granite R2 multilingual, already audited, or mmBERT) on
  Vane 1's licensed data, with labels from our teacher (`mistral-small3.1`) instead of a reranker with MS MARCO in
  its lineage.
