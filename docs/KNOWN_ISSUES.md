# Known issues and backlog

Things we know about but haven't fixed or built yet. Newest first within each section. When an item is
done, delete it here and mention it in `CHANGELOG.md`.

## Known issues

- **Reranking is too slow for small NAS CPUs.** The multilingual default (`BAAI/bge-reranker-v2-m3-int8`)
  takes ~2 s per question for the top 10 on 2 cores (1.1 s on 4, 0.7 s on 8 Zen 4 cores;
  `evals/results/rerankers-threads-2026-11-23.md`), so `NAI_RERANKER=auto` keeps it off below 8 effective
  cores and the NithronOS template sets it off. Nithron Loupe 1 (a distilled bge) should make it cheap
  enough to run on NAS CPUs. Its ONNX build comes from `onnx-community/bge-reranker-v2-m3-ONNX`, whose card
  states no license (base model Apache-2.0); Loupe 1 will ship our own export.
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

## Hand-over: NithronOS template sync (for the session that owns NithronOS)

NithronOS's copy of the nAI template (`usr/share/nithronos/apps/templates/nai/`, added in NithronOS commit
`47def8c`) lags behind `packaging/nithronos/nai/` here (checked 2026-11-23). Changes needed:

1. `compose.yaml`: add `NAI_NAS_PLATFORM=nithronos` (the value the adapter registry uses for NithronOS) and
   change the reranker default from `auto` to an explicit `off` (`NAI_RERANKER=${RERANKER:-off}`): NAS CPUs
   need about 2 s per question for reranking.
2. `schema.json`: `RERANKER` default `off`, enum `off`/`auto`/`on`, new description.
3. Nothing else differs in `compose.yaml` or `schema.json` (the template README is NithronOS's own catalog
   text and isn't synced).

Safe with today's images: nai-core 0.4.0/0.5.0 ignore `NAI_NAS_PLATFORM` and treat `off` as off; existing
installs that stored `true`/`false` keep working with newer nAI versions too. Apply from the NithronOS repo
root with `git apply nithronos-nai.patch` (it applies cleanly to NithronOS `47def8c`):

```diff
--- a/usr/share/nithronos/apps/templates/nai/compose.yaml
+++ b/usr/share/nithronos/apps/templates/nai/compose.yaml
@@ -25,9 +25,10 @@
       - ${SHARES_PATH:-/srv/shares}:/shares:ro
     environment:
       - NAI_AUTH_ENABLED=true
+      - NAI_NAS_PLATFORM=nithronos
       - NAI_SOURCES_ALLOWED_ROOTS=["/shares"]
       - NAI_EMBEDDINGS_ENABLED=true
-      - NAI_RERANKER=${RERANKER:-auto}
+      - NAI_RERANKER=${RERANKER:-off}
       - NAI_OCR_ENABLED=${OCR_ENABLED:-true}
       - NAI_OCR_LANGUAGES=${OCR_LANGUAGES:-eng+deu}
       # Generated answers (optional). Without a model, nAI answers with exact quotes.
--- a/usr/share/nithronos/apps/templates/nai/schema.json
+++ b/usr/share/nithronos/apps/templates/nai/schema.json
@@ -69,12 +69,12 @@
     "RERANKER": {
       "type": "string",
       "title": "Reranking",
-      "description": "Sharper result ordering at some CPU cost. 'auto' enables it on capable hardware.",
-      "default": "auto",
+      "description": "Re-scores the top 10 results with a multilingual reranker. Off by default on NithronOS (NAS CPUs: about 2 s per question). 'auto' turns it on only on fast machines (8+ cores, 8+ GB RAM); 'on' forces it.",
+      "default": "off",
       "enum": [
+        "off",
         "auto",
-        "true",
-        "false"
+        "on"
       ]
     },
     "OCR_ENABLED": {
```

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
