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

## What NithronOS must fix for nAI

Recorded 2026-11-21 in NithronOS's `NAI_INTEGRATION.md` (owned by the NithronOS session; on its milestones):

- **Data-dir ownership:** NithronOS chowns app folders to `nos:nos`, but the nAI container runs as PUID 1000,
  so nAI can't write its data directory.
- **Share read access:** the shares mounted into nAI must be readable by the container user.
- **Container-name networking:** nAI reaches Ollama and other services by container name; the NithronOS app
  network must resolve those names.
- **Memory cap:** NithronOS's template renderer gives apps a 1024M memory limit by default; nAI needs more
  (the template sets an explicit 3g limit). Measured in round 7 with 0.7.0's default model (granite 97m) on a
  2-CPU / 4-GB profile: peak ~1.8 GB with reranking off, ~3.3 GB with it on; hand-over item 4 updates the form text.

## Hand-over: NithronOS template sync (for the session that owns NithronOS)

NithronOS's copy of the nAI template (`usr/share/nos/apps/templates/nai/`, added in NithronOS commit
`47def8c`) lags behind `packaging/nithronos/nai/` here (checked 2026-11-23; items 1–5 sent as one patch to the
NithronOS session on 2026-11-26, open until NithronOS has them). Changes needed:

1. `compose.yaml`: add `NAI_NAS_PLATFORM=nithronos` (the value the adapter registry uses for NithronOS) and
   change the reranker default from `auto` to an explicit `off` (`NAI_RERANKER=${RERANKER:-off}`): NAS CPUs
   need about 2 s per question for reranking.
2. `schema.json`: `RERANKER` default `off`, enum `off`/`auto`/`on`, new description.
3. **Version 0.7.0 (published 2026-11-23; was 0.6.0 in round 5):** point the template at the 0.7.0 image (TrueNAS
   adapter, runs as another uid, Granite default model, keyword-only mode below 2.5g). From the NithronOS repo root:
   `sed -i 's/NAI_VERSION:-0.4.0/NAI_VERSION:-0.7.0/g' usr/share/nos/apps/templates/nai/compose.yaml`
   (image tag and the `nos.app.version` label); in `schema.json` set `NAI_VERSION` `"default": "0.7.0"` and the
   enum to `"0.7.0", "0.7", "0.6.0", "0.6", "0.5.0", "0.4.0", "latest"`; set the catalog entry's
   `version: "0.7.0"`. This repo's copy (`packaging/nithronos/`) has these values since round 8.
4. **Memory text (0.7.0):** in `schema.json` set the `MEMORY_LIMIT` description to "Container memory limit. nAI
   0.7.0 peaks around 1.8 GB (reranking off, the default here) and 3.3 GB with reranking on: keep at least 3g, use
   5g if you turn reranking on. Below 2.5g nAI runs keyword-only (no semantic search)." (default stays `3g`;
   the second sentence is 0.7.0's keyword-only mode, `NAI_EMBEDDINGS=auto`, the image default, so
   `compose.yaml` needs no new variable).
5. `compose.yaml` header comment: update `Source:` URL to `https://github.com/Nithron-Intelligence/nAI`
   (repo transferred 2026-11-24). Keep `image: ghcr.io/nithron/nithronai/nai-core:...` for 0.7.0 and earlier
   unless those tags are mirrored to `ghcr.io/nithron-intelligence/nai/nai-core`; switch to the new
   registry path once its package is public (0.7.1, the first release published there).
6. Nothing else differs in `compose.yaml` or `schema.json` (the template README is NithronOS's own catalog
   text and isn't synced).

Safe with today's images: nai-core 0.4.0/0.5.0 ignore `NAI_NAS_PLATFORM` and treat `off` as off; existing
installs that stored `true`/`false` keep working with newer nAI versions too. Apply from the NithronOS repo
root with `git apply nithronos-nai.patch` (it applies cleanly to NithronOS `47def8c`):

```diff
--- a/usr/share/nos/apps/templates/nai/compose.yaml
+++ b/usr/share/nos/apps/templates/nai/compose.yaml
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
--- a/usr/share/nos/apps/templates/nai/schema.json
+++ b/usr/share/nos/apps/templates/nai/schema.json
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
