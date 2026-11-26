# Vane 1 training-data plan (round 9)

> Status: plan and pipeline, 2026-11-24. Decision of the human (2026-11-24): scale Vane 1's training data to tens
> of thousands of pairs or more, from sources that meet the data rules, with `mistral-small3.1` as the teacher.
> The pilot had 1,875 pairs. Rules: [data rules](ROADMAP.md#principles), [register](MODEL_AND_DATA_LICENSES.md)
> ("Data rule for Vane 1 training data"). Code: [`training/embed/`](../../training/embed/).

## Target

**60,000 filtered pairs** for the first full Vane 1 run (32× the pilot), built so it can grow to 150,000 without
changing the pipeline. Every pair is (query, positive passage, up to 3 mined hard negatives).

| Axis | Target share | Why |
|---|---|---|
| Passage language | en, de, sv, fr, pt 20 % each | nai-bench's five languages; Granite is multilingual already, the gain we want is on these. Spanish, Italian and Dutch can be added later as a 10 % slice. |
| Query language | 55 % same as the passage, 45 % another of the five | Cross-language is the weak spot (v1 dev cross-language Hit@5 0.643 keyword-only, 0.714 hybrid). |
| Passage origin | 55 % real public texts, 45 % teacher-written NAS-like documents | Real text keeps the model honest on real writing; synthetic documents cover household/office files that are not public. |
| Query style | ~40 % question, ~30 % keywords, ~30 % "find the file" | Prompt `pairs-v2`; "find" queries are how people look for a file on a NAS. |
| Per passage | at most 6 queries (filter cap), 3 requested | Breadth over depth. |

Planning figure before measuring was ~2.6 kept pairs per passage (the pilot); measured with pairs-v2 it is ~4.4,
so the target needs ~13,600 passages (see "Throughput" below).

## Sources and licenses

Licenses checked on official pages on 2026-11-24 unless noted. Each downloaded file is recorded with URL,
license, author, date, size and SHA-256 (`fetch_public.py` → `training/manifests/*.json`).

| Source | What | License / legal basis (verified) | Conditions | Share |
|---|---|---|---|---|
| EU law and publications via the Publications Office (CELLAR, `publications.europa.eu/resource/celex/…`) | Regulations, directives, consumer and housing law, in all five languages | EU-owned content: CC BY 4.0 ([Publications Office copyright notice](https://op.europa.eu/en/web/about-us/legal-notices/publications-office-of-the-european-union-copyright): "licensed under the Creative Commons Attribution 4.0 International licence"); legal texts reuse under Commission Decision 2011/833/EU (cited by [data.europa.eu](https://data.europa.eu/copyright-notice) and [DGT-TM](https://joint-research-centre.ec.europa.eu/language-technology-resources/dgt-translation-memory_en)) | Attribution "© European Union", indicate changes; third-party content (images, logos) excluded | ~25 % |
| DGT Translation Memory | Aligned sentence pairs of EU law in 24 languages | Commission Decision of 12 Dec 2011: the Commission "cedes its non-exclusive rights free of charge" ([DGT-TM page](https://joint-research-centre.ec.europa.eu/language-technology-resources/dgt-translation-memory_en)) | Re-user must state the source URL, the update date, and that "the European Commission retains ownership of the data" | ~5 % (cross-language sentence pairs as extra positives, used sparingly: short) |
| German federal law (gesetze-im-internet.de) | Statutes and ordinances | Public domain: § 5 Abs. 1 UrhG, "Gesetze, Verordnungen, amtliche Erlasse … genießen keinen urheberrechtlichen Schutz" ([§ 5 UrhG](https://www.gesetze-im-internet.de/urhg/__5.html)) | None for Abs. 1 texts (Abs. 2 "other official works" carry source-citation and no-alteration duties: we only take Abs. 1 texts) | ~7 % |
| Swedish statutes (data.riksdagen.se, SFS) | Laws and ordinances | 9 § upphovsrättslagen: "Upphovsrätt gäller inte till 1. författningar, 2. beslut av myndigheter …" ([SFS 1960:729](https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/lag-1960729-om-upphovsratt-till-litterara-och_sfs-1960-729/)) | Maps, art, music and poems inside official documents stay protected (9 § second paragraph): plain statute text only | ~6 % |
| US federal works (govinfo.gov: CFR, Federal Register; agency consumer guides) | Regulations and plain-language guides | Public domain in the US: 17 U.S.C. § 105, "Copyright protection … is not available for any work of the United States Government" ([§ 105](https://www.law.cornell.edu/uscode/text/17/105)) | Only works by federal employees (not contractor or third-party material inside); protection abroad is not addressed by § 105 | ~6 % |
| Public-domain books (Project Gutenberg mirror `gutenberg.pglaf.org`) | Novels, essays, non-fiction in the five languages, authors who died before 1956 (PD in the EU and the US) | Public domain (author death date per book); PG's own license and trademark terms **not re-read this round** (gutenberg.org answered 503) | Strip PG header/licence (nai-bench's `gutenberg_strip`), use the mirror, ≥ 1 s between requests; re-read the PG terms before the first download | ~6 % |
| Teacher-written NAS-like documents (`generate_corpus.py --prompt-version corpus-v2`) | Invoices, manuals, notes, contracts, recipes, chats, CSVs … | Written by `mistral-small3.1` (Apache-2.0, approved teacher); we release them as CC0-1.0 | Fictional names, example.org domains, 555 numbers; provenance per file | ~45 % |

Not used: **Europarl** ("We are not aware of any copyright restrictions", [statmt.org/europarl](https://www.statmt.org/europarl/):
no license is granted, so treated as unlicensed); anything CC-BY-SA (Wikipedia, Wikisource, Stack Exchange),
NC or ND; French and Portuguese official texts until their terms are fully verified. Checked 2026-11-24: the
LEGI dataset (consolidated French codes and laws) is listed under "Licence Ouverte / Open Licence" on
[data.gouv.fr](https://www.data.gouv.fr/fr/datasets/legi-codes-lois-et-reglements-consolides/), but the licence
text (Licence Ouverte 2.0) and Légifrance's own reuse page (HTTP 403) were not read. Portugal: CDADC art. 7.º does
not cover laws; art. 8.º n.º 1 says compiled or annotated official texts (art. 3.º n.º 1 c)) "não beneficiam de
protecção" ([CDADC, PGD Lisboa](https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?nid=484&tabela=leis));
the Diário da República terms page returned nothing. Both would add real fr/pt text (today's real fr/pt
passages come only from EU texts); finish the check before using them.

**Excluded by identifier, not only by text:** every document nai-bench uses (v0 and v1, both splits: the CELEX
numbers, CFR parts, SFS numbers, German statutes and Gutenberg book IDs listed in
`evals/nai-bench/v1/sources.json` and both corpus manifests) is refused at download time
(`fetch_public.py` checks every source URL against them). nai-bench v1 holds 23 legal texts and 15 books; we
pick *other* statutes and books, so a gain on v1 dev cannot come from having seen its documents.

## Synthetic documents that do not imitate nai-bench

The pilot's documents (`corpus-v1`: 20 household-paperwork types) are close in style to v1's fictional files
(both are "a family's NAS" invoices, letters and contracts), which makes a gain on v1 dev partly a domain-fit
effect. `corpus-v2` changes the generator, not just the seed:

- ~60 document types beyond paperwork (recipes, vet visits, lab notebooks, router notes, RAID runbooks,
  band setlists, beekeeping logs, board-game rules, startup board minutes, bug logs …);
- crossed with 10 file formats (email with headers, chat export, terse Markdown notes, CSV, checklist,
  README, labelled form …), 12 writer personas, 4 length bands (80–800 words) and a year (2012–2026);
- a distance check after generation: `check_overlap.py` (8-gram overlap and query similarity against all of
  nai-bench) and, during mining, the base model's similarity to v1's files is logged so we can see how close
  the synthetic set sits to the benchmark.

## Pipeline

All scripts are in `training/embed/` (Apache-2.0). Data stays in git-ignored `training/data/vane1/`; the repo
gets the manifests (`training/manifests/`) with sizes, checksums and row counts.

1. **Download** – `fetch_public.py --sources training/sources/vane1-data-v1.json`: byte-exact curl, license per
   file (refuses CC-BY-SA/NC/ND), SHA-256, and the nai-bench source exclusion.
2. **Synthetic corpus** – `generate_corpus.py --prompt-version corpus-v2 --concurrency 4`: resumable, every
   document written and recorded at once.
3. **Chunking** – `make_passages.py`: nAI's own extractor and chunker (1,000 characters, context header), so
   training passages look like what Vane sees in production; license, source and author per passage.
4. **Queries** – `generate_pairs.py --prompt-version pairs-v2 --concurrency 4 --resume` with
   `mistral-small3.1` through Ollama (`OLLAMA_NUM_PARALLEL=4`): rows appended and flushed one at a time.
5. **Filter and deduplicate** – `filter_pairs.py`: training guard, query length, query copied from or contained
   in the passage, language label vs detected language, duplicate queries, near-duplicate passages (5-gram
   Jaccard ≥ 0.8, merged), cap 6 queries per passage; a report of every drop reason.
6. **Overlap check** – `check_overlap.py --write-clean`: 8-gram overlap with all nai-bench texts and questions
   (v0, v1 dev and v1 test read as raw text), query similarity to every nai-bench question.
7. **Hard negatives** – `mine_negatives.py` (ROCm container) with Granite R2 97m: never the positive or another
   passage of the same document (all its language versions: a translation of the positive is a positive), ranks
   3–50 among passages of *other* documents, score < 0.95 × the positive's (likely false negatives dropped);
   3 negatives per pair. Each row also gets `positive_rank` (passages the base model scores above the positive)
   for a later consistency filter. `train.py --file-negatives --hard-negatives N` trains on them instead of
   mining during training (rows with fewer than N are left out; see batch 1 below).
8. **Manifest** – `data_manifest.py`: path, bytes, SHA-256, rows for every data file → `training/manifests/`.
9. **Training guard** – `train.load_pairs` refuses rows not marked `use: training`, eval-only rows, forbidden
   authors (Claude, GPT, Gemini …) and anything under `evals/nai-bench`.

## Keeping the evaluation honest

- **v1 dev** stays the yardstick; the **test split is never loaded** until the human decides a final run.
- **A held-out slice of real documents** that nai-bench doesn't contain: 5 % of the downloaded *documents*
  (whole files, chosen by hash, never chunks of a training file) are set aside before query generation, with
  queries from a *different* model (`qwen2.5:7b`, the bench judge) so the eval queries don't share the
  teacher's phrasing. Reported next to v1 dev as "held-out real" (not a nai-bench number, no release claim).
- **Report per origin:** gains on synthetic-looking v1 files vs on v1's real legal texts and books, so domain fit
  shows up as a split, not as one number.
- **Baselines every time:** plain Granite R2 97m, the previous rc, and keyword-only, embedding-only and hybrid.

## Throughput and time to target

Measured 2026-11-24 on the RX 7900 XTX (24 GB), `mistral-small3.1` Q4_K_M in Ollama 0.40.17-rocm, context 4096,
sample of 180 real passages (`training/data/vane1/throughput/`):

| Step | Setting | Throughput |
|---|---|---|
| Queries (`generate_pairs.py`, pairs-v2) | 1 request at a time | 864 passages/h, 4,666 raw pairs/h |
| | 4 in flight, `OLLAMA_NUM_PARALLEL=4` | 2,107 passages/h, 10,660 raw pairs/h |
| | 8 in flight, `OLLAMA_NUM_PARALLEL=8` (19 GB VRAM) | **2,295 passages/h, 12,292 raw pairs/h** |
| Synthetic documents (`generate_corpus.py`, corpus-v2) | 8 in flight | **268 documents/h** (avg. 340 words → ~5 passages each with nAI's chunker) |

Yield: the teacher writes ~5.1 queries per passage (3 per requested language); `filter_pairs.py` keeps 88 %
(drops: copied queries 11 %, query inside passage, cap) and `check_overlap.py` drops another ~2 % (EU
boilerplate shared with v1's EU texts) → **~4.4 clean pairs per passage, ~10,000 clean pairs per GPU hour**.
Measured mix in the sample: question 37 %, keywords 34 %, find 29 %; 57 % cross-language (above the 45 % target:
`--languages-per-passage` can lower it).

Because a passage yields ~4.4 pairs rather than the pilot's ~2.6, the 60,000 target needs **~13,600 passages**
(not 23,000): ~6,700–7,500 real and ~6,100 synthetic (~1,220 documents).

| Work | GPU time |
|---|---|
| Batch 1: queries for 6,743 real passages (done 2026-11-24) | 2.8 h |
| ~1,420 synthetic documents | ~5.3 h |
| Queries for their ~7,100 passages | ~3.0 h |
| **Total to 60,000 pairs** | **~11 h** (batch 1 done; ~8.3 h left) |

Hard-negative mining (Granite 97m on the GPU) and filtering take minutes.

### Batch 1 (real passages, 2026-11-24 → 26)

6,743 real passages (`select_passages.py --seed 13`: EU 5,000, DE 1,000, SE 800, US 700) → 35,142 raw pairs at
2,393 passages/h → `filter_pairs.py` 31,035 (copied queries 3,726, passage cap 227, query in passage 129,
duplicates 25, merged near-duplicate passages 19) → `check_overlap.py` **29,180 clean pairs** (1,855 dropped:
5.3 %, more than the sample's 2 %, mostly queries naming the same EU directives as nai-bench questions). That is
**4.33 clean pairs per passage**, so the 60,000 target needs ~7,100 more passages (synthetic, since the real
sources are the larger share already). Checksums: `training/manifests/vane1-data-b1.json`.

**Hard negatives: only a third of the pairs get them.** Rows per number of negatives: 0: 19,371, 1: 72, 2: 61,
3: 9,676. Granite's cosine scores are compressed (positive: median 0.858; 4th-best passage of another document:
median 0.855), and the positive is often not the base model's top passage: rank 0 for 23.8 % of pairs, top 10
for 53.1 %, top 50 for 72.5 % (median rank 7). The 0.95 margin therefore removes most candidates. It errs on the
safe side (no near-positive passages as negatives), but `--file-negatives --hard-negatives 1` would train on
only 9,809 of 29,180 pairs. Options, to choose before training:

1. **Keep every pair, hard negatives where they exist:** train with in-batch negatives for all pairs plus mined
   negatives for the third that has them (`train.py` change: rows without negatives stay in).
2. **Consistency filter first:** keep pairs whose positive is in the base model's top *k* (`positive_rank < k`;
   k = 20 keeps 61.7 %, k = 50 keeps 72.5 %) – drops ambiguous queries ("what is the directive about") and
   pushes the target out by the same share.
3. **Looser margin** (0.98–1.0): more negatives, but they score almost like the positive, which is where false
   negatives are; no multilingual reranker with a clean training-data lineage is available to check them.
