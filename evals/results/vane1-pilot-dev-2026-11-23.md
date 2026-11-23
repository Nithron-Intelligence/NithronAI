# Vane 1 pilot (vane-1-rc0) on nai-bench v1 dev – 2026-11-23

**PROVISIONAL, and nothing from this pilot can ship:** the base model's training-data audit needs the human's
decision ([vane1-base-model-audit.md](../../docs/lab/vane1-base-model-audit.md)). v1 **dev split only** (47
answerable questions), no item reviewed, one seed, one small run. With 47 questions the 95 % margin on MRR is
about ±0.1, so read the direction, not the decimals.

**Setup.** Base `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (nAI's default). Pilot: 1 875
query–passage pairs (teacher mistral-small3.1; 570 passages from 100 synthetic NAS-like documents and 16 public
texts, EU reuse and public domain, no CC-BY-SA; 46 % cross-language; training guard and nai-bench overlap check
passed), `train.py` 1 epoch, batch 64, lr 2e-5, max length 256, one mined hard negative, seed 13, 24 steps, 20 s
on the RX 7900 XTX (config `training/configs/vane1-pilot.json`, manifest `training/manifests/vane1-pilot.json`).
No ONNX export; nAI's default model unchanged.

**Method.** `evals/embeddings/dense_eval.py`: the v1 corpus chunked exactly like nAI (10 400 passages, OCR in the
nai-core image), questions and passages embedded with each model (sentence-transformers), best chunk per file,
cosine ranking, no BM25, no 0.3 cutoff. Embedding-only, so compare with nAI's embedding row, not with hybrid.

## Embedding-only retrieval (v1 dev, 47 answerable questions)

| Group | n | base MRR / Hit@1 / Hit@5 | pilot MRR / Hit@1 / Hit@5 |
|---|---|---|---|
| overall | 47 | 0.444 / 0.362 / 0.532 | **0.613 / 0.489 / 0.766** |
| same language | 33 | 0.448 / 0.364 / 0.515 | 0.586 / 0.455 / 0.727 |
| **cross-language** | 14 | 0.435 / 0.357 / 0.571 | **0.676 / 0.571 / 0.857** |
| lookup | 12 | 0.625 / 0.583 / 0.667 | 0.854 / 0.750 / 1.000 |
| table/scan-OCR | 10 | 0.323 / 0.300 / 0.300 | 0.393 / 0.300 / 0.500 |
| multi-hop | 11 | 0.370 / 0.182 / 0.545 | 0.469 / 0.273 / 0.636 |
| de | 14 | 0.379 / 0.286 / 0.500 | 0.579 / 0.429 / 0.714 |
| en | 7 | 0.550 / 0.429 / 0.714 | 0.683 / 0.571 / 1.000 |
| sv | 6 | 0.333 / 0.167 / 0.500 | 0.525 / 0.333 / 0.833 |
| fr | 10 | 0.425 / 0.400 / 0.400 | 0.618 / 0.500 / 0.700 |
| pt | 10 | 0.548 / 0.500 / 0.600 | 0.658 / 0.600 / 0.700 |

For reference, nAI's own runs on the same 62 dev items ([v1-dev-stage0](v1-dev-stage0-2026-11-23.md)): embedding
MRR 0.494 / Hit@5 0.575, hybrid 0.720 / 0.894, hybrid + reranker 0.911 / 0.936 (cross-language Hit@5 0.643,
0.714, 0.786). The offline base numbers (0.444 / 0.532) are a little below nAI's embedding row because of the
different harness (no source/heading boost, best-chunk-per-file ranking); the base-vs-pilot comparison uses the
same harness for both.

## Reading it

- Every category and language improves, cross-language most (Hit@5 0.571 → 0.857), from 24 training steps.
  That fits the round-4 diagnosis: the base model ranks long distractors above short household documents.
- **Caveats:** tiny dev set; one seed; the synthetic documents are household/small-office texts like v1's
  fictional files (no shared text: the overlap check passed, but the style is close), so part of the gain may be
  domain fit rather than general cross-language ability; held-out pairs from the pilot data: accuracy@5 0.41 →
  0.64. Next would be several seeds, a larger and more varied corpus, and a hybrid run in nAI (needs the ONNX
  export, deliberately not done this round).
