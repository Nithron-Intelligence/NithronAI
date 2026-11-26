# nAI as a NithronOS app

This folder is a NithronOS app catalog template, in the same format as the templates in the
NithronOS repo (`usr/share/nos/apps/templates/<id>/`).

| File | Goes to (NithronOS repo) |
|------|--------------------------|
| `nai/compose.yaml`, `nai/schema.json` | `usr/share/nos/apps/templates/nai/` |
| `catalog-entry.yaml` | an entry under `entries:` in `usr/share/nos/apps/catalog.yaml` |
| `icon.svg` | `usr/share/nos/apps/templates/nai/icon.svg` |

## What the app does

- Mounts the NithronOS shares (`/srv/shares`) **read-only** at `/shares`. nAI never modifies files.
- After install, open the app (default port 8090), create the first account (it becomes admin)
  and add shares under **Sources**, e.g. `/shares/documents`. Each source is indexed in place and
  kept in sync by a file watcher plus periodic incremental rescans.
- Restrict a source to groups (e.g. `finance`) so only members can find its files.
- Search works without a GPU. Generated answers need a model: Ollama on the NAS, Ollama on a PC
  with a GPU (`LLM_BASE_URL=http://<pc>:11434`), any OpenAI-compatible server, or a cloud API.
  Without one, answers are exact quotes from the files.
- The embedding model (~0.5 GB) is downloaded into the app's data folder on first start. Until it
  is ready, search is keyword-only; the app is healthy meanwhile.

## Permissions

The container runs as `PUID:PGID` (default 1000:1000). That user needs read access to the shares
you add as sources; files it cannot read are skipped and logged. `/srv/apps/nai/data` must be writable by it
(NithronOS currently chowns app folders to `nos:nos`; see `NAI_INTEGRATION.md` in the NithronOS repo).

Added to the NithronOS repo on 2026-11-21 (uncommitted there; see its `NAI_INTEGRATION.md`).
Keep this folder and the NithronOS copy in sync.

## Before publishing

1. ~~Tag a release (`v0.4.0`) so `release.yml` publishes the image.~~ Done 2026-11-22:
   `ghcr.io/nithron/nithronai/nai-core:0.4.0` is public (amd64 + arm64).
2. ~~Copy the files above into the NithronOS repo.~~ Done 2026-11-21; commit it there.

## Later (Phase 2)

- Map NithronOS share ACLs (owners/readers, users/groups) to nAI source groups automatically.
- Sign-in with NithronOS accounts instead of separate nAI accounts.
- Embed the nAI UI in the NithronOS dashboard.
