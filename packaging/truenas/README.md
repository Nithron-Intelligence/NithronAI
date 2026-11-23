# nAI on TrueNAS (custom app)

Status: first step of the TrueNAS adapter (2026-11-23): nAI runs as a custom app and can **read** the
shares TrueNAS knows about through its API. It never changes anything on TrueNAS, and it doesn't sync
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
   give it a **read-only administrator role** (on current releases: Privilege "Read-Only Administrator";
   check the exact name in your version's docs at `/api/docs/` or https://api.truenas.com).
2. Sign in as an admin, open the user menu > **My API Keys** (or **Credentials > API Keys**), create a key
   **for that user**, and copy it. A TrueNAS API key works like a password: anyone with it can do whatever
   that user may do, which is why the user is read-only.
3. In the app's YAML set `NAI_TRUENAS_URL=wss://<truenas-host>/api/current` and `NAI_TRUENAS_API_KEY=<key>`.
   - nAI only connects over `wss://` with certificate verification. With TrueNAS's default self-signed
     certificate, export the certificate (**Credentials > Certificates**), put it in the nAI data dataset,
     and set `NAI_TRUENAS_CA_FILE=/app/data/truenas-ca.pem`. The host name in the URL must match the
     certificate. nAI never falls back to an unverified connection.
4. Check: `GET /sources/discover` (admin) shows `"platform": "truenas"` and `"status": {"connected": true,
   "version": "..."}`. If not, `status.detail` says why (the key is never shown or logged).

nAI calls only `auth.login_with_api_key`, `system.info`, `sharing.smb.query` and `sharing.nfs.query`
(JSON-RPC 2.0 over WebSocket; the REST API is deprecated since TrueNAS 25.04). Any other method is
refused in code.

## Manual test (TrueNAS VM)

1. Install TrueNAS (25.04 or later) in a VM, create a pool `tank` with datasets `documents` (with a few PDFs)
   and `photos`, an SMB share for `documents` and an NFS share for `photos`.
2. Create the read-only user and API key as above; install nAI with only `documents` mounted.
3. As the nAI admin, call `GET /sources/discover` (UI, or curl with an nAI API key as a bearer token): expect `documents` (mounted) and
   `photos` (`"source": "nas-api", "mounted": false`), and `status.connected: true` with the version.
4. Negative checks: a wrong key gives `connected: false` with "rejected the API key"; `ws://` in the URL is
   refused; removing `NAI_TRUENAS_CA_FILE` with a self-signed certificate gives a TLS error, not a silent
   insecure connection; `docker logs` never shows the key.
