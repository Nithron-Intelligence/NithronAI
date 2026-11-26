# Releasing nAI

Tags `vX.Y.Z` trigger `.github/workflows/release.yml`, which builds and pushes
`ghcr.io/nithron-intelligence/nai/nai-core:X.Y.Z` (amd64 + arm64) and creates the GitHub Release.
(Releases `0.4.0`–`0.7.0` were published under `ghcr.io/nithron/nithronai/nai-core` before the 2026-11-24
move to `Nithron-Intelligence` and the 2026-11-26 rename of the repository to `nAI`; keep or update compose templates accordingly once images are published or
mirrored under `ghcr.io/nithron-intelligence/nai/nai-core` and make sure the new package is set to
public.) The Release
body is the commit list since the previous tag plus GitHub's generated notes, not the CHANGELOG entry;
paste the CHANGELOG section into the Release by hand if you want it there.

1. On `main`, make sure the version agrees everywhere. `tests/test_version.py` checks it in CI:
   - `apps/nai-core/app/config.py` (`app_version`) and `apps/nai-core/app/__init__.py` (`__version__`)
   - the version badge in `README.md`
   - a `## [X.Y.Z]` section in `CHANGELOG.md`
2. In `CHANGELOG.md`, replace "not tagged yet" with today's date and fix the compare links at the bottom:
   `[X.Y.Z]` → `compare/vPREVIOUS...vX.Y.Z` and `[Unreleased]` → `compare/vX.Y.Z...HEAD`.
3. CI is green on `main`.
4. Tag and push (maintainer only): `git tag -a vX.Y.Z -m "nAI X.Y.Z" && git push origin vX.Y.Z`.
5. When the image is published, update the NithronOS template to the new version, in this repo and in
   the NithronOS repo copy: `packaging/nithronos/nai/compose.yaml` (`NAI_VERSION` default and the
   `nos.app.version` label), `packaging/nithronos/nai/schema.json` (default and allowed versions) and
   `packaging/nithronos/catalog-entry.yaml`. The template only points at published images, which is why
   it lags behind `main` until step 4 is done.
