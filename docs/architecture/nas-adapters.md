# NAS adapter layer

> Status: design + first step implemented (2026-11-23). Decision record:
> [ADR-0004](../ADRs/0004-nas-adapter-layer.md).

nAI runs on any NAS OS. Everything that depends on a particular NAS lives behind one interface, the
**NAS adapter**, so nai-core never imports platform code directly. NithronOS is the reference platform:
it gets the first and deepest adapter. Plain Docker on any Linux box is the fallback that always works.

## What an adapter covers

| Concern | Core (all platforms) | Adapter (per platform) |
|---|---|---|
| Shares | Sources = folders under `NAI_SOURCES_ALLOWED_ROOTS`, indexed in place | Discover the NAS's shares (names, paths, which are mounted into the container) and suggest them as sources |
| Accounts | Local nAI accounts (always available), API keys | Optional sign-in with the NAS's own accounts (OIDC, LDAP, or the NAS API) |
| Permissions | nAI groups + `allowed_groups` per source, enforced before top-k | Read the NAS's share permissions and map users/groups to nAI groups (read-only sync) |
| Management | – | Optional MCP server over the NAS management API (Stage 3 tool use): read-only first, then actions with user confirmation |
| Packaging | One container image, `docker-compose` | The platform's app format (catalog entry, template, package) |

Rules:
- Local nAI accounts and manual sources always work, so a missing or broken adapter never locks anyone out.
- Adapters are **read-only towards the NAS** except the management MCP server, and that only acts after
  the user confirms in nAI.
- An adapter declares what it supports (capabilities); the UI only shows what is available.
- Credentials for NAS APIs are per-installation settings, stored like other secrets, never logged.

## Interface sketch

Implemented today (`apps/nai-core/app/nas/`): `NasAdapter`, `ShareCandidate`, `Capabilities`, the generic
and NithronOS adapters, and `GET /sources/discover`. Everything else is a sketch for later steps.

```python
@dataclass(frozen=True)
class ShareCandidate:
    name: str            # display name, e.g. "Familie"
    path: str            # path inside the nAI container, e.g. "/shares/Familie"
    source: str          # "mount" (found under an allowed root) or "nas-api"
    already_added: bool  # an nAI source already covers it


@dataclass(frozen=True)
class Capabilities:
    share_discovery: bool = True
    nas_sign_in: bool = False          # sign in with NAS accounts
    permission_sync: bool = False      # NAS share permissions -> nAI groups
    management_mcp: bool = False       # MCP server over the NAS management API


class NasAdapter(Protocol):
    name: str                          # "generic", "nithronos", "truenas", ...
    capabilities: Capabilities

    def discover_shares(self, roots: list[str], existing: list[str]) -> list[ShareCandidate]: ...

    # Later steps (not implemented yet):
    # def authenticate(self, username: str, password: str) -> NasIdentity | None
    # def oidc_config(self) -> OidcConfig | None
    # def share_permissions(self) -> list[SharePermission]      # share -> [(principal, read|write|none)]
    # def map_to_groups(self, perms: list[SharePermission]) -> dict[str, list[str]]  # nAI group -> users
    # def management_tools(self) -> list[McpTool]               # Stage 3
```

The adapter is chosen with `NAI_NAS_PLATFORM` (`generic` by default; packaging sets it, e.g. the NithronOS
template sets `nithronos`). Auto-detection is deliberately not used yet: guessing a platform from the
environment inside a container is unreliable.

## Platforms

Each platform's packaging format and auth/permission model, from the official docs (checked 2026-11-23).

| Platform | App packaging | Accounts and sign-in | Share permissions | Management API | Adapter plan |
|---|---|---|---|---|---|
| **NithronOS** (reference) | Catalog app: `compose.yaml` + `schema.json` + catalog entry (`packaging/nithronos/`) | NithronOS accounts (sign-in planned) | NithronOS share ACLs (to be mapped to nAI groups) | NithronOS API (`nos_client_contract.json` in the NithronOS repo) | Step 1 (done: adapter + template sets `nithronos`), then permission sync, sign-in, MCP |
| **Plain Docker** (any Linux) | `infra/docker-compose.yml` | nAI accounts only | Filesystem permissions of the mounted folders | none | `generic` adapter (done) |
| **TrueNAS SCALE / Community Edition** | Apps are Docker Compose. Catalog apps in `truenas/apps` use `app.yaml`, `questions.yaml` and Jinja2 compose templates; users can also install any app as **custom YAML** (a Compose file with `services:`) [1][2][3] | Local users and directory services (AD/LDAP); per-user API keys [4] | Datasets with NFSv4 or POSIX ACLs; SMB shares have their own share ACL on top, both must allow access [5][6] | JSON-RPC 2.0 over WebSocket (the REST API is deprecated since 25.04); API keys via `auth.login_ex` [4][7] | Custom-YAML install first; catalog submission later; permission sync reads dataset ACLs via the API |
| **Unraid** | Docker templates (XML) distributed through Community Applications; repository needs `ca_profile.xml` [8][9][10] | Share users (no WebGUI access) and root; Unraid API (built in since 7.2) with API keys, roles, and OIDC sign-in [11][12][13] | Per-share SMB security: Public / Secure / Private with per-user read/write [14][15] | Unraid API (GraphQL) with scoped API keys, including a `SHARE` resource [11][12] | Template XML (easy); sign-in via the Unraid API's OIDC support; share security via the API |
| **Synology DSM 7.2+** | Container Manager projects (Docker Compose) [16]; or an SPK package built with the DSM toolkit (`PkgCreate.py`), which can wrap containers [17][18]. Container Manager isn't available on every model (many ARM models lack it) [19] | DSM users, LDAP/AD; **SSO Server** offers OIDC to third-party apps (domain + valid TLS required) [20][21] | Shared-folder permissions for local/LDAP/AD users and groups | DSM Web API (not covered here; to research before step 4) | Compose project first; SPK for Package Center later; sign-in via SSO Server OIDC |
| **QNAP QTS** | Container Station applications (Docker Compose YAML) [22]; containerized QPKG built with QDK (`qbuild`) that runs Compose via Container Station [23] | Local users, LDAP, AD (domain security) [24][25] | Shared-folder permissions per user/group; Deny > Read/Write > Read Only [26] | Not found in official docs during this check | Container Station app first; QPKG later; LDAP for sign-in |
| **OpenMediaVault 7/8** | Docker via the omv-extras `openmediavault-compose` plugin (Compose files in a shared folder) [27][28] | Local users (PUID/PGID for containers), LDAP via plugin | Shared-folder privileges (none/read/read-write) plus POSIX ACLs [29] | RPC (`ShareMgmt.getPrivileges`, …; admin only) [30] | Compose file + docs; privileges readable via RPC |

Sources:
[1] [TrueNAS: Installing Custom Apps](https://apps.truenas.com/managing-apps/installing-custom-apps/) ·
[2] [TrueNAS: Custom App Screens](https://www.truenas.com/docs/scale/apps/installcustomappscreens/) ·
[3] [truenas/apps CONTRIBUTIONS.md](https://github.com/truenas/apps/blob/master/CONTRIBUTIONS.md) ·
[4] [TrueNAS 25.04 version notes](https://www.truenas.com/docs/scale/25.04/gettingstarted/scalereleasenotes/) ·
[5] [TrueNAS: Configuring ACL Permissions](https://www.truenas.com/docs/scale/scaletutorials/datasets/permissionsscale/) ·
[6] [TrueNAS: Setting Up SMB Private Dataset Shares](https://www.truenas.com/docs/scale/shares/smb/smbprivatedatasetshare/) ·
[7] [TrueNAS: Feature Deprecations](https://www.truenas.com/docs/scale/26/gettingstarted/deprecations/) ·
[8] [Unraid docs: Community Applications](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/community-applications/) ·
[9] [Unraid Community Apps: submission help](https://ca.unraid.net/submit/help) ·
[10] [unraid-apps/template starter kit](https://github.com/unraid-apps/template) ·
[11] [Unraid API: Using the API](https://docs.unraid.net/API/how-to-use-the-api/) ·
[12] [Unraid API: Programmatic API key management](https://docs.unraid.net/API/programmatic-api-key-management/) ·
[13] [Unraid API: OIDC provider setup](https://docs.unraid.net/API/oidc-provider-setup/) ·
[14] [Unraid docs: Shares](https://docs.unraid.net/unraid-os/using-unraid-to/manage-storage/shares/) ·
[15] [Unraid docs: User management](https://docs.unraid.net/unraid-os/system-administration/secure-your-server/user-management/) ·
[16] [Synology: Container Manager Project](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project?version=7) ·
[17] [Synology DSM 7 Developer Guide (PDF)](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Os/DSM/All/enu/DSM_Developer_Guide_7_enu.pdf) ·
[18] [Synology developer guide: Compile Docker Package](https://help.synology.com/developer-guide/examples/compile_docker_package.html) ·
[19] [Synology KB: Container Manager 24.0.2-1630 availability](https://kb.synology.com/en-sg/DSM/tutorial/Why_is_Container_Manager_1630_not_available_on_my_Synology_NAS) ·
[20] [Synology KB: Set up OIDC with SSO Server](https://kb.synology.com/en-uk/DSM/tutorial/set_up_oidc_for_dsm_in_sso_server) ·
[21] [Synology: SSO Server technical specifications (DSM 7.2)](https://www.synology.com/en-global/dsm/7.2/software_spec/sso_server) ·
[22] [QNAP: How to use Container Station 3](https://www.qnap.com/en/how-to/tutorial/article/how-to-use-container-station-3) ·
[23] [qnap-dev/containerized-qpkg](https://github.com/qnap-dev/containerized-qpkg) ·
[24] [QNAP QTS 5.2: Managing AD and LDAP users](https://docs.qnap.com/operating-system/qts/5.2.x/en-us/managing-ad-and-ldap-users-6EF4B88D.html) ·
[25] [QNAP QTS 4.5: Domain Security](https://docs.qnap.com/operating-system/qts/4.5.x/en-us/GUID-5933D0DB-174E-41E2-BDAE-D9A8213F517F.html) ·
[26] [QNAP QTS 5.0: Conflicts in Shared Folder Permissions](https://docs.qnap.com/operating-system/qts/5.0.x/en-us/conflicts-in-shared-folder-permissions-54363A37.html) ·
[27] [omv-extras wiki: openmediavault-compose (OMV 7)](https://wiki.omv-extras.org/doku.php?id=omv7%3Aomv7_plugins%3Adocker_compose) ·
[28] [omv-extras wiki: Docker in OMV 7](https://wiki.omv-extras.org/doku.php?id=omv7%3Adocker_in_omv) ·
[29] [openmediavault 8.x docs: Shared Folders](https://docs.openmediavault.org/en/8.x/administration/storage/sharedfolders.html) ·
[30] [openmediavault source: ShareMgmt RPC service](https://github.com/openmediavault/openmediavault/blob/master/deb/openmediavault/usr/share/openmediavault/engined/rpc/sharemgmt.inc)

Gaps to research before building those adapters: Synology DSM Web API for share permissions, QNAP's
management API, and each platform's ARM/x86 coverage for the nAI image (amd64 + arm64 today).

## Steps

1. **Done (2026-11-23):** `app/nas/` with the interface, `generic` and `nithronos` adapters, share discovery
   (`GET /sources/discover`, admin only), `NAI_NAS_PLATFORM` setting; the NithronOS template sets
   `NAI_NAS_PLATFORM=nithronos`.
2. **Plain Docker / OMV / Unraid packaging** (no code): a documented `docker-compose.yml`, an Unraid template
   XML, an OMV compose example. Low risk, broadens reach immediately.
3. **TrueNAS packaging**: custom-YAML install guide, then a `truenas/apps` catalog submission.
4. **Permission sync** (read-only): `share_permissions()` + `map_to_groups()` for NithronOS first, then
   TrueNAS (dataset ACLs via JSON-RPC) and Unraid (share security via the API). Synced groups are marked as
   NAS-managed; nAI never writes permissions back.
5. **NAS sign-in**: OIDC first (Unraid API, Synology SSO Server, any IdP), so most platforms share one code
   path; NithronOS accounts through its API.
6. **Management MCP** (Stage 3): one common tool interface (`list_shares`, `get_disk_health`,
   `list_snapshots`, …) implemented per adapter; NithronOS first.
7. **Synology and QNAP packages** (SPK, QPKG) once there is demand; Compose projects work before that.

nai-bench and the models never depend on an adapter: the benchmark only needs a folder of files.
