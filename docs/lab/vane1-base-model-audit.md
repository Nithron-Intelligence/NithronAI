# Vane 1 base-model training-data audit

> Audit of `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, nAI's default embedding model and the
> chosen base for Nithron Vane 1 ([stage 1 plan](stage1-embedding-finetune.md) §1). Written 2026-11-23 (round 5,
> decision 4: no full Vane 1 training run and no public release until this audit passes). Not legal advice.

## Verdict: **needs the human's decision** (it does not pass a "clean data" bar)

The model itself is Apache-2.0 (model card), but its lineage includes training data whose terms say
**non-commercial research only** (MS MARCO, Flickr30k captions) and a lot of **CC-BY-SA** data (SNLI,
Stack Exchange, Wikipedia-derived sets, WikiAtomicEdits, WikiMatrix), plus TED talks under TED's usage policy.
Whether the terms of training data bind the weights of a model trained on it is legally unsettled; the model's
authors released the weights under Apache-2.0 regardless. So the audit cannot say "passes", and it does not
prove "fails": it is a risk decision for the human.

**What it means for Vane 1:** a fine-tune inherits the base model's lineage. If the human decides this lineage is
not acceptable for a commercial release, Vane 1 cannot be built on this base (nor on most public embedding
models, which use MS MARCO-style data too) and the realistic options are listed at the end. **The same question
applies to nAI today**: 0.6.0 downloads and uses this model by default (via fastembed), so the decision covers
the shipped product, not only Vane 1.

## Lineage

The model card says the model maps sentences to 384-d vectors, was "trained by sentence-transformers" and points
to the SBERT paper ([model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
license `apache-2.0`). The SBERT docs describe it as the "Multilingual version of
sentence-transformers/paraphrase-MiniLM-L12-v2, trained on parallel data for 50+ languages"
([pretrained models](https://www.sbert.net/docs/sentence_transformer/pretrained_models.html)), made with the
multilingual knowledge distillation of Reimers & Gurevych 2020 ([arXiv 2004.09813](https://arxiv.org/abs/2004.09813)).
Three layers of data are involved:

1. **Student initialization:** a multilingual MiniLM checkpoint (`microsoft/Multilingual-MiniLM-L12-H384`,
   license `mit` on its card; it uses XLM-R's tokenizer; the paper's experiments use XLM-R as the student).
   Its pre-training data (web-scale multilingual text) is not audited here.
2. **Teacher:** `paraphrase-MiniLM-L12-v2`, "trained on the following datasets: AllNLI, sentence-compression,
   SimpleWiki, altlex, msmarco-triplets, quora_duplicates, coco_captions, flickr30k_captions,
   yahoo_answers_title_question, S2ORC_citation_pairs, stackexchange_duplicate_questions, wiki-atomic-edits"
   ([SBERT paraphrase training docs](https://www.sbert.net/examples/sentence_transformer/training/paraphrases/README.html)).
   The student learns to reproduce the teacher's embeddings, so the teacher's data shapes the model.
3. **Multilingual distillation (parallel data):** the released model's exact mix is not documented ("parallel
   data for 50+ languages"). The paper's experiments use OPUS corpora: "GlobalVoices, TED2020, … WikiMatrix,
   Tatoeba, Europarl, JW300, OpenSubtitles2018, UNPC" (arXiv 2004.09813, §4).

## Datasets

"Verified" = license read on a primary page this round (URL given). "Unverified" = the page could not be read
this round; the note says what still needs checking.

| Dataset (layer) | License / terms | Source | Allows commercial model training? | Flags |
|---|---|---|---|---|
| MS MARCO (teacher) | "intended for non-commercial research purposes only"; rights end on violation | [microsoft.github.io/msmarco](https://microsoft.github.io/msmarco/), verified | **No** (non-commercial) | non-commercial |
| Flickr30k captions (teacher) | "for … non-commercial research and/or educational purposes"; images under Flickr terms | [Denotation Graph page](https://shannon.cs.illinois.edu/DenotationGraph/), verified | **No** (non-commercial) | non-commercial |
| SNLI (teacher, in AllNLI) | CC-BY-SA-4.0 | [HF card stanfordnlp/snli](https://huggingface.co/datasets/stanfordnlp/snli), verified | Yes, with share-alike/attribution questions | **CC-BY-SA** |
| MultiNLI (teacher, in AllNLI) | mixed: CC-BY-3.0, CC-BY-SA-3.0, MIT, other | [HF card nyu-mll/multi_nli](https://huggingface.co/datasets/nyu-mll/multi_nli), verified | Mostly yes | partly **CC-BY-SA**, "other" |
| Stack Exchange duplicates (teacher) | "All user content … is cc-by-sa 4.0 licensed" | [archive.org/details/stackexchange](https://archive.org/details/stackexchange), verified | Yes, with share-alike/attribution questions | **CC-BY-SA** |
| WikiAtomicEdits (teacher) | CC-BY-SA-4.0 | [HF card google-research-datasets/wiki_atomic_edits](https://huggingface.co/datasets/google-research-datasets/wiki_atomic_edits), verified | as above | **CC-BY-SA** |
| SimpleWiki, altlex (teacher) | Wikipedia-derived (Wikipedia text is CC-BY-SA) | unverified (no license on the SBERT dataset cards) | as above | likely **CC-BY-SA** |
| COCO captions (teacher) | unverified (terms page did not render) | cocodataset.org/#termsofuse | check | unclear |
| Quora duplicates (teacher) | unverified (Kaggle/Quora pages unreadable) | kaggle.com/c/quora-question-pairs | check | unclear |
| Yahoo Answers title–question (teacher) | unverified | — | check (Yahoo Webscope data is usually research-only) | unclear, possibly non-commercial |
| S2ORC citation pairs, sentence-compression (teacher) | unverified | — | check | unclear |
| WikiMatrix (parallel) | "CC-BY-SA 4.0" | [OPUS legacy page](https://opus.nlpl.eu/legacy/WikiMatrix.php), verified | as above | **CC-BY-SA** |
| TED2020 (parallel) | "Please respect the TED Talks Usage Policy" | [OPUS legacy page](https://opus.nlpl.eu/legacy/TED2020.php), verified | check the TED policy (not read this round) | possibly non-commercial / no-derivatives |
| Tatoeba (parallel) | "CC BY 2.0 FR" | [OPUS legacy page](https://opus.nlpl.eu/legacy/Tatoeba.php), verified | Yes (attribution) | — |
| GlobalVoices, Europarl, OpenSubtitles2018, UNPC, JW300 (parallel) | unverified (OPUS pages unreadable this round) | — | check; JW300's availability/terms especially | unclear |

Even if only one of these datasets was in the released model's actual training mix, the lineage includes
non-commercial terms: MS MARCO and Flickr30k are named explicitly for the teacher.

## What the human needs to decide

1. **Accept the lineage risk** for nAI's default model and for Vane 1 (the model license is Apache-2.0; training
   data terms binding the weights is unsettled; this model is widely used commercially). Then the audit counts as
   passed by decision and the Vane 1 plan continues unchanged, with the lineage stated in the model card.
2. **Or reject it.** Then: (a) nAI should offer/default to a different embedding model whose training data is
   documented and clean, if one exists (to check: most multilingual embedding models, including
   `multilingual-e5-*` and `bge-m3`, also train on MS MARCO-style data), and (b) Vane 1 becomes a larger project:
   train our own student from a permissive pre-trained encoder (e.g. the MIT multilingual MiniLM checkpoint)
   using only rule-compliant data (synthetic teacher text, EU parallel texts, CC-BY/CC0 parallel corpora such
   as Tatoeba), i.e. a "Vane 2"-sized effort, and the pilot below is a learning exercise only.
3. Whether decision 3 (no CC-BY-SA in *our* training data) should also apply to the *base model's* lineage.
   Under option 1 it does not; under option 2 it does.

Until the human decides, the round-5 pilot runs as planned (decision 4) but **nothing from it can ship**.

## Still to check (if option 1)

The unverified rows above (COCO, Quora, Yahoo Answers, S2ORC, sentence-compression, GlobalVoices, Europarl,
OpenSubtitles, UNPC, JW300, the TED policy), and the student checkpoint's pre-training data. None of them can
turn the verdict into a clean pass, because MS MARCO and Flickr30k are verified non-commercial.
