# Known issues and backlog

Things we know about but haven't fixed or built yet. Newest first within each section. When an item is
done, delete it here and mention it in `CHANGELOG.md`.

## Known issues

- **No multilingual reranker by default.** The bundled cross-encoder (`Xenova/ms-marco-MiniLM-L-6-v2`) is
  English-only and trained on MS MARCO (non-commercial data terms), and it didn't improve nai-bench, so
  reranking is off by default everywhere (`config.py`, `infra/docker-compose.yml`, the NithronOS template).
  Candidates are compared in `evals/results/rerankers-*.md`; Nithron Loupe 1 is meant to replace it.
- **MCP clients that only do OAuth can't connect.** nAI's MCP server accepts API keys (bearer tokens);
  clients that require OAuth (for example Claude Desktop custom connectors) can't use it yet.
- **Vector search is brute force in memory.** Fine up to roughly 10^5–10^6 chunks; beyond that, move to an
  index (e.g. sqlite-vec) before memory and latency grow too much.
- **The Docker image is about 1.3 GB** (LiteLLM + onnxruntime). `INSTALL_FULL=false` builds a smaller
  search-only image without LLM answers and OCR.
- **OCR languages.** The image ships Tesseract `eng` and `deu` only. Swedish, French and Portuguese scans are
  read with those models (nai-bench's Swedish receipt still works, but accents suffer). Adding
  `tesseract-ocr-swe`/`-fra`/`-por` costs a few MB each.
- **Test warning:** Starlette warns that using `httpx` for `TestClient` is deprecated in favour of `httpx2`.
  Harmless for now.

## Backlog

### Index e-mail files (`.eml`, `.mbox`)

NAS users often keep exported mail (`.eml` files, `.mbox` archives from Thunderbird or mail backups). nAI
skips them today. The removed `packages/toolpacks/email_pack.py` (deleted 2026-11-23, still in git history
before that date) had a stdlib-only `EmailParser`: header decoding (RFC 2047), address extraction, plain-text
body with an HTML-to-text fallback, attachment listing, `parse_eml`, `parse_mbox` and an IMAP fetcher.

To do it properly:
- Port only `parse_eml` / `parse_mbox` into `app/utils/extractors.py` as an extractor that returns
  `Section`s: one section per message, with subject/from/date as the heading and the body as text.
  Leave IMAP out: nAI indexes files in place, it doesn't fetch mail.
- Attachments: index text attachments (PDF, DOCX) through the existing extractors, with the parent message
  in the context header; skip the rest.
- Access: a mailbox file may hold one person's private mail; it follows the source's `allowed_groups` like
  any file, so document that admins should put mail in a restricted source.
- Tests with small fixture `.eml`/`.mbox` files (including non-UTF-8 headers), plus nai-bench questions
  once v1 exists.
- Use only the Python standard library (`email`, `mailbox`): no new dependencies.
