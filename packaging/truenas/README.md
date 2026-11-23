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

1. **Apps > Discover Apps**, open the menu next to **Custom App**, choose **Install via YAML**.
2. Paste [`compose.yaml`](compose.yaml), change the `/mnt/tank/...` paths to your datasets (one read-only
   line per dataset), and save. TrueNAS only checks the YAML syntax, so double-check the paths.
3. Open `http://<truenas>:8000`; the first account you create becomes the admin. Add sources in the
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
3. In the app's YAML set `NAI_TRUENAS_URL=wss://<truenas-host>/api/current` and `NAI_TRUENAS_API_KEY=<key>`.
   - nAI only connects over `wss://` with certificate verification and never falls back to an unverified
     connection. The host name or IP in the URL must be in the certificate.
   - TrueNAS's default certificate (`truenas_default`) is self-signed for **`localhost` only**, so it fails
     for `wss://<truenas-ip>/...` or `wss://truenas.local/...` ("IP address mismatch"). TrueNAS 25.10 can no
     longer create a CA itself, so make a small CA and a certificate for the name/IP nAI uses (e.g.
     [`scripts/truenas-vm/make-cert.sh`](../../scripts/truenas-vm/make-cert.sh) `<dir> IP:192.168.1.10
     DNS:truenas.local`), import it under **Credentials > Certificates** (Import Certificate), select it as
     the web UI certificate (**System > General Settings > GUI**), put the CA's `ca.pem` in the nAI data
     dataset and set `NAI_TRUENAS_CA_FILE=/app/data/truenas-ca.pem`. An ACME (Let's Encrypt) certificate
     for a real host name works without a CA file. (The VM test did these steps over the API with
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
`path`) matched; the test fixtures are now recorded from 25.10.8. Not covered yet: running nAI as a custom app
inside TrueNAS (Apps), and permission sync (not implemented).
