# nAI on TrueNAS (custom app)

Status: first step of the TrueNAS adapter (2026-11-23): nAI runs as a custom app and can **read** the
shares TrueNAS knows about through its API. **Tested against TrueNAS Community Edition 25.10.8 on
2026-11-23** (VM test below). It never changes anything on TrueNAS, and it doesn't sync
permissions yet (manage nAI groups in nAI). Design: [docs/architecture/nas-adapters.md](../../docs/architecture/nas-adapters.md).

## 1. Datasets

1. Create a dataset for nAI's own data, e.g. `tank/apps/nai`, with the **Apps** permission preset (gives
   the built-in `apps` user and group, UID/GID 568, access).
2. Make sure the `apps` group can **read** each dataset nAI should search (e.g. an ACL entry for group
   `apps` with Read). nAI mounts them read-only and never writes to them.

## 2. Install the app

Use an image newer than 0.5.0: 0.5.0 predates the TrueNAS adapter, and when TrueNAS runs it as the `apps`
user it can't download its embedding model (fixed after 0.5.0, see CHANGELOG "Image runs as any user").

1. If Apps were never used on this TrueNAS: **Apps > Configuration > Choose Pool** (e.g. `tank`) first.
2. **Apps > Discover Apps**, open the menu next to **Custom App**, choose **Install via YAML**.
3. Paste [`compose.yaml`](compose.yaml), change the `/mnt/tank/...` paths to your datasets (one read-only
   line per dataset), and save. TrueNAS only checks the YAML syntax, so double-check the paths.
4. Open `http://<truenas>:8000`; the first account you create becomes the admin. Add sources in the
   **Sources** tab (they are the folders under `/shares`).

## 3. Optional: share discovery through the TrueNAS API

With this, nAI's **Sources > Discover** also lists TrueNAS shares that aren't mounted into the app yet
(marked "not mounted"), so you can see what to add to the YAML.

1. **Credentials > Users**: add a user just for nAI (e.g. `nai-reader`) with no shell and no SMB access, and
   put it in the built-in group **`truenas_readonly_administrators`** (privilege "Read-Only Administrator";
   tested on 25.10.8). TrueNAS itself refuses writes for this user (`[EACCES] Not authorized`).
2. Sign in as an admin, open the user menu > **My API Keys** (or **Credentials > API Keys**), create a key
   **for that user**, and copy it. A TrueNAS API key works like a password: anyone with it can do whatever
   that user may do, which is why the user is read-only.
3. In the app's YAML set `NAI_TRUENAS_URL=wss://<truenas-ip-or-name>/api/current` and
   `NAI_TRUENAS_API_KEY=<key>`. Use the TrueNAS machine's LAN IP or name, not `localhost` (inside the app,
   `localhost` is nAI's own container).
   - nAI only connects over `wss://` with certificate verification and never falls back to an unverified
     connection. The host name or IP in the URL must be in the certificate.
   - TrueNAS's default certificate (`truenas_default`) is self-signed for **`localhost` only**, so it fails
     for `wss://<truenas-ip>/...` or `wss://truenas.local/...` ("IP address mismatch"). TrueNAS 25.10 can no
     longer create a CA itself, so make a small CA and a certificate for the name/IP nAI uses (e.g.
     [`scripts/truenas-vm/make-cert.sh`](../../scripts/truenas-vm/make-cert.sh) `<dir> IP:192.168.1.10
     DNS:truenas.local`), import it under **Credentials > Certificates** (Import Certificate), select it as
     the web UI certificate (**System > General Settings > GUI**), put the CA's `ca.pem` in the nAI data
     dataset and set `NAI_TRUENAS_CA_FILE=/app/data/truenas-ca.pem`. An ACME (Let's Encrypt) certificate
     for a real host name works without a CA file. Certificates need Subject and Authority Key
     Identifiers when nAI runs on Python 3.13+ (strict verification; the image uses 3.11), which
     `make-cert.sh` adds. (The VM test did these steps over the API with
     `certificate.create` / `system.general.update`; the UI menu names above weren't checked.)
4. Check: `GET /sources/discover` (admin) shows `"platform": "truenas"` and `"status": {"connected": true,
   "version": "..."}`. If not, `status.detail` says why (the key is never shown or logged).

nAI calls only `auth.login_with_api_key`, `system.info`, `sharing.smb.query` and `sharing.nfs.query`
(JSON-RPC 2.0 over WebSocket; the REST API is deprecated since TrueNAS 25.04). Any other method is
refused in code.

## Manual test (TrueNAS VM)

Reproducible setup and checks: [`scripts/truenas-vm/`](../../scripts/truenas-vm/README.md) (QEMU/KVM VM,
pool `tank`, `tank/documents` with sample files over SMB, `tank/photos` over NFS, read-only user `nai-reader`
with an API key, own CA). `test_adapter.py` runs nAI's adapter code with only the read-only key.

**Result, TrueNAS Community Edition 25.10.8, 2026-11-23** (ISO SHA-256 checked against truenas.com), all
checks passed by host name (`wss://localhost:8443`) and by IP (`wss://127.0.0.1:8443`):

| Check | Result |
|---|---|
| Discovery with `NAI_TRUENAS_CA_FILE` | connected, version `25.10.8`; `documents` (SMB, mounted) and `photos` (NFS, `"source": "nas-api"`, not mounted) |
| Allow-list | `user.query` refused in code before anything is sent |
| Read-only user on the server | a write sent past the allow-list on purpose: `[EACCES] Not authorized` |
| Without the CA file | `CERTIFICATE_VERIFY_FAILED` (self-signed / unable to get local issuer), no insecure fallback |
| Default certificate by IP | `IP address mismatch` (it names only `localhost`; see section 3) |
| `ws://` URL | refused before connecting |
| Wrong key | `connected: false`, "TrueNAS rejected the API key" |
| Key in logs | absent from all log records at DEBUG level (incl. websockets) and from all output |

Real-API differences fixed in the adapter: error replies carry the useful text in `error.data.reason`
(`message` is just "Method call error"); websockets 17 deprecates calling `connect()` without a context
manager. The response shapes nAI reads (`system.info`, `sharing.smb.query`, `sharing.nfs.query` with a single
`path`) matched; the test fixtures are now recorded from 25.10.8. Permission sync is not implemented.

### Custom app (TrueNAS Apps), 2026-11-23

nAI built from `lab/stage-0` (a local image loaded with `docker save | ssh … docker load`, no registry),
installed with [`compose.yaml`](compose.yaml) through `app.create` (the API behind **Install via YAML**) by
[`scripts/truenas-vm/install_app.py`](../../scripts/truenas-vm/install_app.py), checked by
[`test_app.py`](../../scripts/truenas-vm/test_app.py). All checks passed:

| Check | Result |
|---|---|
| Container | runs as `568:568`; `/mnt/tank/documents` and `/mnt/tank/photos` mounted read-only (a write gives "Read-only file system"); `/mnt/tank/apps/nai` (Apps preset) writable; healthy |
| Search | semantic search on (`fastembed`, multilingual MiniLM) after the image fix below |
| Discovery from inside the app | `platform: truenas`, connected over `wss://10.0.2.15/api/current` (the VM's own IP) with the read-only key and `NAI_TRUENAS_CA_FILE=/app/data/truenas-ca.pem`; version 25.10.8 |
| Indexing | `/shares/documents`: 4 documents, status ok |
| Answers (extractive, no LLM) | "Where is the guest Wi-Fi access point?" → `wifi-notes.txt`; "When is the next boiler service due?" → `heating-maintenance.md` |
| Key in logs | absent from all 72 lines of the app's log |

Found and fixed:
- **The image didn't work as another user.** TrueNAS Apps run it as `apps` (568), whose `HOME` is `/`: the
  embedding model download failed (Hugging Face cache in `/.cache`) and the bundled NLTK data in the
  private `/home/nai` was unreadable, so nAI silently fell back to keyword search. Fixed in the
  Dockerfile (`HF_HOME=/app/data/.cache/huggingface`, NLTK data in `/opt/nltk_data`), with a test.
- **Guide:** choose the Apps pool first; `NAI_TRUENAS_URL` must use the TrueNAS IP or name, not
  `localhost`; the certificate must name that IP (TrueNAS 25.10 can't make one, see section 3); the
  SMB-preset dataset needed an NFSv4 ACL entry for group `apps` (Read), the generic dataset (mode 755)
  was readable as is.

Seen, not fixed: a German question about the English note on the boiler ("Wann ist die nächste Wartung des
Heizkessels fällig?") found nothing, because its cosine similarity stays under `NAI_EMBEDDINGS_MIN_SCORE`
(0.3) with the default MiniLM model; the same question in English works. Cross-lingual retrieval on short
notes is what Vane 1 is for (nai-bench v1 measures it).
inside TrueNAS (Apps), and permission sync (not implemented).
