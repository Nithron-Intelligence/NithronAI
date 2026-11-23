# ADR-0004: nAI runs on any NAS (NAS adapter layer)

- Status: accepted (2026-11-23)
- Amends: [ADR-0003](0003-product-scope.md) ("ship as a NithronOS app first") and
  [ADR-0002](0002-nithron-ai-lab-direction.md) (Stage 3 target)

## Context

nAI was planned as a NithronOS catalog app. Its users and buyers, though, run many NAS systems: TrueNAS,
Unraid, Synology DSM, QNAP QTS, OpenMediaVault and plain Linux boxes with Docker. All of them can run
containers, but they differ in packaging, accounts, share permissions and management APIs (see
[docs/architecture/nas-adapters.md](../architecture/nas-adapters.md)).

## Decision

1. nAI is a **standalone product for any NAS OS** and can be sold. NithronOS stays the **reference
   platform**: supported first and most deeply.
2. Everything platform-specific goes behind a **NAS adapter** interface (`app/nas/`): share discovery,
   optional NAS sign-in, read-only mapping of share permissions to nAI groups, an optional management MCP
   server, and packaging. nai-core never imports platform code directly.
3. Local nAI accounts and manually added sources always work; adapters only add convenience and
   integration.
4. Adapters are read-only towards the NAS, except management actions that the user confirms in nAI.
5. Packaging targets, in order: NithronOS catalog, plain Docker Compose, then the platform with the best
   effort/reach ratio (see the business doc), then the others.
6. The lab's Stage 3 becomes the **NAS agent model**, trained against one common tool interface; the
   NithronOS adapter implements it first. nai-bench never assumes a particular NAS.

## Consequences

- The first step is small: interface, `generic` and `nithronos` adapters, share discovery,
  `NAI_NAS_PLATFORM`. No refactor of sources, auth or access control.
- Each new platform needs packaging, docs and a test install on that platform before it is advertised.
- Permission sync and NAS sign-in are per-platform work; OIDC is preferred where available so one
  implementation covers several platforms.
- Licensing for other platforms (vendors bundling nAI) needs review; see
  `docs/business/product-and-licensing.md`.
