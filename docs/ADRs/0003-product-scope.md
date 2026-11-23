# ADR-0003: Product scope

- Status: accepted (2026-11-21, recorded 2026-11-23). The "NithronOS app first" part is amended by
  [ADR-0004](0004-nas-adapter-layer.md): nAI supports any NAS OS, with NithronOS as the reference platform.

## Context

By late 2026 there are many good general chat front ends for local and hosted models (Open WebUI,
AnythingLLM, LibreChat and others). nAI's strengths are elsewhere: it indexes NAS folders in place, keeps
them in sync, respects who may see which folder, searches across languages and OCR'd scans, and answers
with citations to the original file and page. It runs as one container on modest hardware.

## Decision

1. **Don't compete with general chat UIs.** nAI is "the AI that knows your NAS": search and cited answers
   over your own files. Chat-UI features (personas, prompt libraries, multi-model chat, plugins) are out of
   scope.
2. **Keep nAI's own chat UI simple**: ask, chat with citations, sources, system status. People who want a
   richer chat UI connect one to nAI through the OpenAI-compatible API or MCP server.
3. **Ship as a NAS app first**: the NithronOS catalog app was the first target (amended by ADR-0004 to
   "any NAS, NithronOS first-class").
4. **Integrate with the NAS over time**: share permissions mapped to nAI groups, NAS account sign-in, and
   an MCP server for the NAS management API (read-only first, then confirmed actions).

## Consequences

- Work on interoperability (OpenAI-compatible API, MCP, API keys) takes priority over chat-UI features.
- Product quality is measured on NAS-style questions (nai-bench), not on general chat benchmarks.
- The UI stays small enough to maintain without a front-end framework.
