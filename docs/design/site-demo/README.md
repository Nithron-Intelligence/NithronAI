# nAI demo run for the website (draft, awaiting Thiago's approval)

**Sample data: nAI 0.7.0, a demo corpus.** The run is real: nAI as built from its v0.7.0 tag answered these
questions, and `run.json` holds what it returned, unchanged. The files are not real: they are a demo corpus of
fictional documents, written with Claude for the nAI website. They are not part of nai-bench and are not used to
train or evaluate anything. Nothing here goes to the website until Thiago has approved it; the website labels the
picture "Sample data", with the detail "nAI 0.7.0, a demo corpus".

## The corpus (`corpus/`, built by `build_corpus.py`)

| File | What it is |
|---|---|
| `Household/Insurance/car-insurance-2027.pdf` | A text PDF: a car insurance renewal notice (renewal date, premium, excess) |
| `Household/Heating/boiler-service-log.md` | Markdown: a boiler's service log (last visit, next one due, warranty) |
| `Household/Internet/Glasfaser-Vertrag.txt` | Plain text, in German: a fibre contract (term, monthly price, notice period) |
| `Work/Invoices/invoice-2027-041.pdf` | A text PDF: a small studio's invoice (items, VAT, total, due date) |
| `Photos/receipt-hardware-store.jpg` | A photo of a till receipt, read by OCR (Tesseract, in the shipped image) |

Every name, number and address is made up and looks it: "Example", "Beispiel" and "Demo" names, `.example`
domains, a zeroed IBAN, policy and customer numbers starting with `DEMO`. Amounts are in euro, dates in 2027.
`build_corpus.py` writes the same files again, byte for byte (reportlab and Pillow, build time only).

## The run (`run.json`)

- **nAI:** version 0.7.0, commit `974e25dedbfade3a58270e8e92fe80c648535983` (tag `v0.7.0`), as a Docker image
  built from that commit with `apps/nai-core/Dockerfile`.
- **Mode:** hybrid search (keywords and embeddings, fused) with the embedding model
  `ibm-granite/granite-embedding-97m-multilingual-r2` (nAI's default); **reranker off**; **no language model**:
  the answer is nAI's extractive answer, its own excerpts of the files. Top 3 passages.
- **Why the reranker is off:** 0.7.0 turns its reranker on by default on a machine this size, and that reranker is
  not cleared for use in a Nithron product. Later nAI keeps it off unless asked. The run with 0.7.0's default
  (reranker on) is kept for the record in `run-0.7.0-default-reranker.json`; with it, the second question put the
  boiler log first and the contract second.
- **Scores:** nAI's fusion scores (reciprocal rank fusion of the keyword and the embedding ranking). They order the
  passages; they are not probabilities, and close scores (0.0328 against 0.0320) mean a close call.
- **Times:** the wall time of each `/ask` call on the same machine, after one untimed warm-up query, so they
  measure a running nAI and not the loading of its models.

Questions, and the file nAI ranked first:

1. "When does the car insurance renew?": `car-insurance-2027.pdf`, page 1.
2. "What is the notice period for the internet contract?": `Glasfaser-Vertrag.txt` (an English question, a German
   file: this is the embeddings at work).
3. "How much is invoice 2027-041 and when is it due?": `invoice-2027-041.pdf`, page 1.

## Repeating it

From the repository root, with Docker:

```sh
git worktree add --detach /tmp/nai-v0.7.0 v0.7.0
docker build -f /tmp/nai-v0.7.0/apps/nai-core/Dockerfile -t nai-core:0.7.0-demo /tmp/nai-v0.7.0
docker run -d --name nai-site-demo -p 127.0.0.1:8765:8000 \
  -v nai-site-demo-data:/app/data -v "$PWD/docs/design/site-demo/corpus:/shares/demo:ro" \
  -e NAI_AUTH_ENABLED=false -e NAI_EMBEDDINGS_ENABLED=true -e NAI_LLM_ENABLED=false -e NAI_RERANKER=off \
  -e 'NAI_SOURCES_ALLOWED_ROOTS=["/shares"]' nai-core:0.7.0-demo
python3 docs/design/site-demo/run_demo.py --base http://127.0.0.1:8765 \
  --commit "$(git rev-parse 'v0.7.0^{commit}')" --image "nai-core:0.7.0-demo (docker build of tag v0.7.0)" \
  --note "Run with NAI_RERANKER=off: 0.7.0 turns its reranker on by default, and that reranker is not cleared for this use (see README.md)."
docker rm -f nai-site-demo && docker volume rm nai-site-demo-data && git worktree remove /tmp/nai-v0.7.0
```

The first start downloads the embedding model into the data volume. `run_demo.py` adds the corpus
as a NAS folder, waits until it is scanned and every passage is embedded, and asks each question once. Passage
order and scores repeat exactly; times vary with the machine.
