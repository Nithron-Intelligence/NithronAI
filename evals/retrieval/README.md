# nAI retrieval evaluation

Scores nAI's search (`POST /search`) on the answerable questions of
[nai-bench](../nai-bench/README.md). The old five placeholder cases (`test_cases.json`) are gone.

## Metrics

All metrics are **document level**: several chunks of the same file count once, in the rank of the
first one.

| Metric | Meaning |
|---|---|
| Recall@K | share of the question's gold files found in the top K files |
| Precision@K | share of the top K files that are gold files |
| Hit@K | 1 if at least one gold file is in the top K |
| MRR | 1 / rank of the first gold file, averaged |
| nDCG@K | rank-discounted gain over the gold files |
| Page Hit@K | 1 if a top-K chunk comes from a gold file **and** its gold page (questions with paged gold sources only) |

Results are reported overall, by category and by question language, for each search method.

## Usage

Start nAI with the corpus visible to the server (the easiest way is `infra/compose.bench.yaml`, which
mounts it at `/shares/nai-bench`), then:

```bash
python evals/retrieval/eval_retrieval.py \
  --index-corpus /shares/nai-bench \
  --methods bm25,embedding,hybrid \
  --output retrieval.json
```

`--index-corpus` creates a source named `nai-bench` for that path (as the server sees it) and waits until
the scan and all embeddings are done. Leave it out if the corpus is already indexed. Use `--api-key` when
auth is on.

For the full run (retrieval + answer quality + metadata + Markdown summary) use
[`../run_baseline.py`](../run_baseline.py).
