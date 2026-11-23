# Licensing options for nAI itself

> **Needs review by a lawyer.** Draft for discussion, 2026-11-23. Not legal advice; the NCL is governed by
> German law (venue Berlin). This page lists trade-offs only and recommends nothing. Scope: the nai-core
> service and web UI. The lab parts are already decided (code in `evals/` and `training/` Apache-2.0,
> nai-bench items CC-BY-4.0; see `NOTICE`). Background: [product-and-licensing.md](product-and-licensing.md).

## The three options

| | **A. NCL + commercial license** (today) | **B. AGPL-3.0 + commercial license** (dual license) | **C. Open core** |
|---|---|---|---|
| What it is | Source-available, non-commercial only (`LICENSE`); everything commercial needs an agreement (`COMMERCIAL.md`) | The same code under AGPL-3.0 *or* a paid commercial license, at the user's choice | Core (indexing, search, answers, UI) under an OSI license (e.g. Apache-2.0 or AGPL-3.0); business features in a separate, commercially licensed module |
| What competitors may do | Read and fork for non-commercial use only; no selling, hosting, prebuilt images or app catalogs without an agreement (§§ 2–3) | Fork, sell and host, but must publish their changes under AGPL, including for network use (AGPL § 13); a closed product needs the commercial license | With a permissive core: anything with the core, including closed products; with an AGPL core: as in B. The paid module stays closed |
| Unraid Community Apps | Not eligible: CA requires "an OSI-approved LICENSE file at the repository root" [1]; an older CA policy also asks that apps made by the template author be open source [2] | Eligible (AGPL-3.0 is OSI-approved) | Eligible for the core (template points at the core image) |
| Community trust | Lower with open-source users ("source-available", not open source); clear for buyers | Higher (real open source); some companies avoid AGPL entirely | High for the core; perceived "crippleware" risk if the line between core and paid moves later |
| Selling to NAS vendors | Every vendor needs an agreement (bundling = commercial use + binary redistribution); simple to explain | Vendors that can't comply with AGPL (closed firmware, own modifications) buy the commercial license; others may ship under AGPL for free | Vendors may bundle a permissive core for free; revenue only from the paid module and support. An AGPL core works like B |
| GHCR image | Must be licensed explicitly: today public images conflict with `BINARIES-EULA.md` (subscription) — either a free personal-use grant or authenticated images | Public image under AGPL (with source offer); a separate commercial image/EULA for licensees, if needed | Public core image under its OSI license; the paid module as a separate image or plug-in with its own EULA |
| Contributions / CLA | NCL § 4(c) already lets Nithron relicense contributions (works for A) | Needs the right to relicense contributions into the commercial edition: NCL § 4(c) covers past NCL contributions; outside contributors would need a CLA or DCO + license grant | Core contributions under the core license; the paid module is Nithron-only (no CLA needed there) |
| Effort to switch | None | New `LICENSE` text across Nithron products (today `LICENSE` is shared byte-identically with NithronOS), CLA process, review of dependencies' compatibility | Code split into core and module, two license files, packaging per edition |

## What the AGPL history means

`NOTICE` says versions up to and including commit `66fa142` were released under **AGPL-3.0-only**; copies
obtained then stay under AGPL. For each option:

- **A:** Anyone may keep using, forking and even selling that old AGPL snapshot under AGPL terms; the NCL
  only applies to later versions. That snapshot predates Phase 0 (no auth, no sources), so its practical
  value is low, but it can't be withdrawn.
- **B:** Continuity: returning to AGPL makes the old and new code compatible again. Nithron's own later
  contributions can be released under AGPL freely; third-party contributions made under the NCL are covered
  by NCL § 4(c) relicensing (to verify).
- **C:** If the core becomes AGPL, same as B. If it becomes permissive (Apache-2.0), code from the AGPL era
  written by third parties (if any) would need their consent or a rewrite; Nithron-authored code can be
  relicensed.

Open legal questions for all options: whether NCL § 4(c) is enforceable as a relicensing grant under German
law, whether any outside contributions exist before or after `66fa142`, and whether the AGPL-only versions
included third-party code that can't be relicensed.

Sources:
[1] [Unraid Community Apps: submission help](https://ca.unraid.net/submit/help) (current requirements:
public, active repository with an OSI-approved LICENSE at the root, `ca_profile.xml`, one template XML per
app) ·
[2] [Unraid forums: CA – Application Policies](https://forums.unraid.net/topic/87144-ca-application-policies-notes/)
(older policy thread: apps made by the template maintainer must be open source; 2FA on repositories; no
extra commands in templates).
