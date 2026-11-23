# nAI: product and licensing

> Status: draft for discussion, 2026-11-23. Not legal advice. Sections marked **⚖ needs review by a
> lawyer** must be checked by a German-qualified lawyer (the NCL is governed by German law) before anything
> here is acted on. The `LICENSE` file is not changed by this document.

## What we sell

nAI is "the AI that knows your NAS": private search and cited answers over the files on a NAS, running on
the NAS (or a PC next to it), multilingual, with OCR. It is a standalone product for any NAS OS
([ADR-0004](../ADRs/0004-nas-adapter-layer.md)); NithronOS is the reference platform with the deepest
integration.

## Who buys

| Segment | What they want | What they pay for |
|---|---|---|
| **Home users and prosumers** (TrueNAS, Unraid, Synology, QNAP, OMV, NithronOS owners) | Find documents, receipts, manuals across years of files; no cloud | Little or nothing for the basics; convenience features, updates, priority support |
| **Small offices** (2–50 people, often a Synology/QNAP or a TrueNAS box) | Search contracts, invoices, project files with per-group permissions; data stays in the office (GDPR) | A business license per server, support, NAS sign-in and permission sync |
| **NAS OS vendors** (OS or hardware makers who want "AI search" as a built-in feature) | A ready, tested AI layer they can bundle and brand | An OEM / bundling license, per-unit or annual, plus integration support |
| **MSPs and IT service providers** | Deploy and manage nAI for many small clients | An MSP license (per managed node), central management, support SLAs |

## Possible business models

1. **Free community tier + paid features (open core).** Free: indexing, hybrid search, cited answers,
   OCR, the web UI, API keys, OpenAI-compatible API and MCP for personal use. Paid ("nAI Pro/Business"):
   NAS sign-in, permission sync, multi-source admin, audit log, the NAS management agent (Stage 3),
   priority updates, business use.
2. **Commercial license for vendors (OEM).** NAS OS and hardware vendors bundle nAI, optionally
   white-labelled. Per-unit royalty or annual fee; includes integration help and early access to Nithron
   models.
3. **Support subscriptions.** Business and MSP customers: SLA, update channel, help with deployment. Fits
   the existing `COMMERCIAL.md` channels.
4. **Hosted option (later).** A hosted nAI is the opposite of the "private, on your NAS" promise, so only as
   a narrowly defined offer: e.g. a hosted **model endpoint** (Nox on a GPU) that a NAS uses for hard
   questions, opt-in per query, with a clear data-processing agreement. Not a hosted copy of the user's
   files.

Recommendation: start with 1 + 3 (they match the current `COMMERCIAL.md`), add 2 when the first vendor
asks, and keep 4 out until Nox exists and there is demand.

## How the Nithron Community License fits ⚖ needs review by a lawyer

What the current documents say (summary, not legal interpretation):

- **NCL v1.0 (`LICENSE`)**: source-available, **non-commercial only**. Personal/educational/research use and
  contributions are allowed; any commercial use, hosting for third parties, and distribution of prebuilt
  binaries, container images or *app catalogs* need a separate commercial agreement (§§ 2–3).
  Contributors grant Nithron the right to relicense their contributions (§ 4c). German law, venue Berlin.
- **`COMMERCIAL.md`**: business internal use, MSP/reseller rights and white-labelling via a commercial
  agreement; Patreon tiers for individuals get Official Build Artifacts.
- **`BINARIES-EULA.md`**: Official Build Artifacts (images, packages) are licensed per node to subscribers;
  no redistribution or mirroring.

Questions this raises for selling on other platforms (status 2026-11-23: the lab parts now have their own
open licenses, see below; nAI's own license direction is undecided, options in
[licensing-options.md](licensing-options.md)):

1. **NCL is not an open-source license.** Some app stores require one: the Unraid Community Applications
   submission rules ask for a public repository with an **OSI-approved license**
   ([submission help](https://ca.unraid.net/submit/help)). TrueNAS's catalog and others may have similar
   rules (to check). Options: (a) an OSI-licensed thin packaging repo that installs the official image under
   the EULA (does that satisfy the store's intent?); (b) dual licensing (below); (c) ship outside those
   stores (custom YAML / manual templates).
2. **App catalogs are restricted (§ 3.2).** Third parties may not publish catalog entries for nAI without an
   agreement; Nithron publishing its own entries (TrueNAS, Unraid, Synology, QNAP) is fine. Should
   community-maintained templates be explicitly allowed (e.g. a written permission for templates that pull
   the official image)?
3. **Public images vs. the EULA.** The 0.4.0 image is public on GHCR, while the EULA ties Official Build
   Artifacts to a subscription. Either the free tier's image is explicitly licensed for free personal use, or
   images move behind authentication. Today the two documents point in different directions.
4. **"Non-commercial" for home users is fine, but a small office is commercial use** under the NCL
   definition, even for internal use. That matches "business license", but the product page must say it
   clearly.
5. **Vendors bundling nAI** need an OEM agreement covering redistribution of images, branding (trademarks
   § 3.4), the update channel and liability; `COMMERCIAL.md` only mentions MSP/reseller and white-label.

### Is a dual license needed?

Today nAI is effectively **source-available + commercial** (NCL for non-commercial, separate agreement for
everything else). That already *is* a dual model. A second **open-source** license (e.g. AGPL-3.0 or
Apache-2.0 alongside the commercial license) would only be needed if:
- app stores that require OSI licenses become important channels, or
- the community and vendors won't adopt a non-OSI license.

Trade-offs to discuss with the lawyer:
- **NCL + commercial (status quo):** strongest control and simplest to enforce; limits store listings and
  community packaging.
- **AGPL-3.0 + commercial:** OSI-approved (store listings work), vendors and SaaS providers still need a
  commercial license in practice; requires the contributor relicensing grant (already in NCL § 4c) and a CLA
  for outside contributions; AGPL obligations apply to Nithron's own dependencies policy too.
- **Open core:** core under an OSI license, paid features in a separate commercially licensed module.

Recommendation (for discussion, not a decision): keep the NCL for nai-core for now, write the
missing permissions (free personal use of the public image; community templates that pull the official
image), and decide on a dual license once one store listing or one vendor deal depends on it.

## What stays open, what is paid

| Part | Recommendation | Why |
|---|---|---|
| **Nithron models** (Vane, Loupe, Tern, Nox) | **Open weights**, Apache-2.0 (as base licenses allow), on Hugging Face | The lab's reputation and adoption depend on it; models are the proof of the research |
| **nai-bench** (corpus, questions, results) | **Open**, CC-BY-4.0 for what we write; third-party files keep their licenses (statute excerpts public domain) | A benchmark only matters if others can run it and check our claims (principle 4) |
| **Training and eval code** (`training/`, `evals/`) | **Open**, Apache-2.0 (decided 2026-11-23) | Reproducibility of model claims; low commercial risk |
| **Lab reports, datasets we generate** | Open (CC-BY-4.0 or CC0) | Same as models |
| **nai-core** | Source-available (NCL) or open core (see above) | Product revenue |
| **NAS integrations for business** (permission sync, NAS sign-in, management agent, audit) | Paid tier | Clear business value |
| **Official images, signed updates, support** | Paid for business; free personal tier | As in `COMMERCIAL.md` |

⚖ **needs review by a lawyer**: **done 2026-11-23, pending legal review.** `evals/LICENSE` and
`training/LICENSE` (Apache-2.0) and `evals/nai-bench/LICENSE-CC-BY-4.0.txt` hold the official texts, and
`NOTICE` says which paths they cover; the root `LICENSE` (NCL, byte-identical with NithronOS) is unchanged
and covers everything else. Still to check with the lawyer: that the folder licenses validly override the
NCL's "everything in the repository" wording, and that NCL § 4 contributions to those folders can be
offered under Apache-2.0 / CC-BY-4.0.

## Open questions for the owner

1. Licensing direction: status quo NCL + commercial, AGPL + commercial, or open core?
2. Which second platform to support first (recommendation in the final report: TrueNAS; Unraid has the
   OSI-license blocker above).
3. Pricing anchors for the business tier and the OEM license.
4. Do the open parts (`evals/`, `training/`, nai-bench) get their own licenses now?
