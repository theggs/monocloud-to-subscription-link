# MonoCloud to Subscription Link

## Purpose

Generate client subscriptions from MonoCloud nodes and official routing rules,
with optional Tailscale configuration for access to a Tailnet. The planned targets are
Clash/mihomo (Clash Mi first), sing-box MT, and Surge.

The subscription service will generate and serve configuration. The client device
will handle proxy traffic and, when enabled, Tailscale connections directly.
Subscriptions can be used with MonoCloud alone, without configuring or authorizing
Tailscale. Tailscale-specific routes and DNS settings are included only when enabled.

**MonoCloud 1.5 adaptation:** live browser login, service discovery and authenticated
server-list decryption have been verified. The protected subscription for a mixed
Shadowsocks and MonoLite account downloaded successfully and passed mihomo
configuration validation. Live refresh-token rotation and device acceptance for
1.5 are pending. See the
[verification results](docs/clash-verification.md#monocloud-15-account-protocol-adaptation-2026-11-18).

**Original verification:** configuration checks, local token storage, password-grant login,
service discovery, and node retrieval are implemented. The complete account workflow
is tested against a local HTTP server using constructed credentials. Browser login
and reuse of its saved token for service/node discovery have also been verified
against MonoCloud. The browser page provides a protected Clash/mihomo subscription
link and a persistent Tailscale toggle. Both generator modes pass core checks;
Clash Mi 1.0.31.1703 URL import/update, both modes, Tailnet DNS/access and
restart persistence have been verified on iPhone. See
[verification](docs/clash-verification.md).

## Requirements and installation

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency and
  environment management.

From the repository root:

```sh
uv sync --locked
uv run monocloud-subscription --help
```

uv creates a project-specific `.venv/`. HTTP requests use httpx. FastAPI and Uvicorn
serve the login page; PyYAML parses and serializes Clash configuration. cryptography
provides X25519, HKDF-SHA256 and AES-256-GCM for the v2 node response. Ruff is a
development dependency.

## Quick start

Copy the example and fill in your private `monocloud.client_id` and
`monocloud.client_secret` (see [configuration](#configuration-and-private-data)):

```sh
mkdir -p .local
cp config.example.toml .local/config.toml
```

Create `.local/service.env` with a management password you choose; replace the
placeholder below:

```dotenv
MONOCLOUD_WEB_PASSWORD=replace-with-your-own-private-password
```

Start the service:

```sh
chmod 600 .local/config.toml .local/service.env
uv run --env-file .local/service.env monocloud-subscription --config .local/config.toml serve
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The management username is
`admin`; use the password you put in `.local/service.env`. Then follow the page's
steps from account login to **导入客户端**. For LAN access from other devices or HTTPS, see
[deployment](docs/deployment.md).

## Configuration and private data

Configuration uses TOML. Supply its path explicitly with `--config`.

| Setting | Required | Meaning |
| --- | --- | --- |
| `data_dir` | Yes | Nonempty path reserved for runtime data. Relative paths resolve against the configuration file's directory. |
| `template_dir` | No | Explicit local official snapshot directory with `update.json` and `Clash_ss`. Both size and SHA-256 are verified; default is HTTPS download. Relative to TOML. |
| `server.host`, `server.port` | No | Listen address and port; default `127.0.0.1:8080`. CLI flags override them. |
| `server.public_url` | No | Base URL reachable by clients; defaults to the management browser origin. No credentials, query or fragment. |
| `subscription.key` | No | Private random URL-safe key override (32-128 characters); normally generated automatically. |
| `token_file` | No | Token JSON path; defaults to `data_dir/token.json`. An explicit relative path resolves against the configuration file. |
| `monocloud.base_url` | No | HTTPS API root; defaults to the researched MonoCloud API. |
| `monocloud.api_version` | No | `v2` (default) or explicit `legacy`; no automatic downgrade. |
| `monocloud.user_agent` | No | User-Agent header, default `MonocloudGO-1.5.0`. |
| `monocloud.client_version` | No | X-Client-Version header, default `1.5.0`; an empty string omits it. |
| `monocloud.client_id`, `monocloud.client_secret` | For login/refresh | Private OAuth application credentials. |
| `monocloud.response_key_id`, `monocloud.response_key` | For encrypted v2 nodes | Matching response key ID and standard-base64 32-byte shared key; supply both privately. |
| `monocloud.request_context` | Deployment-dependent | Optional already-encoded `X-Request-Context`; not generated or fabricated by this service. |
| `monocloud.client_platform`, `monocloud.os_version`, `monocloud.device_model`, `monocloud.device_model_name` | No | Optional already-encoded device headers, omitted when empty. |
| `clash.mixed_port` | No | Client mixed proxy port, default `7890`; LAN access is disabled in generated configs. |
| `tailscale.enabled` | No | Opt in to Tailscale, default `false`. |
| `tailscale.hostname` | No | Client's Tailnet device name. |
| `tailscale.state_dir` | No | Persistent path on the **client**, default `tailscale`. Never resolved against the server's configuration path. |
| `tailscale.auth_key` | No | Private authorization key; omitted from output if unset. The core then logs a login URL. |
| `tailscale.control_url` | No | Custom HTTPS control server URL, such as Headscale. |
| `tailscale.routes` | No | Subnets the client should reach via the Tailnet; they must be advertised and authorized on other Tailnet devices. Default empty; no exit node or default route is configured. |

With `.local/config.toml` and `data_dir = "data"`, the runtime data location is
`.local/data/`, regardless of the process working directory. Absolute paths are
also supported. Use an absolute configuration path when invoking the installed
command from another directory.

Keep private research, personal configuration, future credentials, and runtime
data in `.local/`, which Git ignores. The first server startup creates
`data_dir/subscription.json` with a random 256-bit URL credential. Preserve this
file to preserve client URLs; it also stores the saved Tailscale enabled override.
If there is no override, the TOML flag is used. Changing TOML alone does not replace
a browser-saved toggle; use the page to change it. Corrupt state fails explicitly
rather than silently resetting it. State updates use owner-only temporary files
and atomic replacement. Run one application worker for this local file store. An external private directory is equally
valid. On POSIX systems new token files have owner-only permissions; token updates
replace the file atomically. Existing directory permissions are left unchanged;
deployers should restrict private configuration and data directories. Atomic
replacement is not a power-loss durability guarantee. Browser login saves the returned
access token, optional refresh token and absolute expiry; passwords and raw
API responses are not persisted. Local configuration containing OAuth client secrets
should also be readable only by its owner. Do not put real credentials or generated
subscriptions in tracked files or issue reports.

### Upgrading account integration to MonoCloud 1.5

Keep the existing private data directory, `subscription.json` and Tailscale state.
Those determine existing subscription links and client identity. Upgrade dependencies
with `uv sync --locked`, set `monocloud.api_version = "v2"` (the new default), and
review old explicit User-Agent/version overrides. Sign in again through the browser
to obtain a refreshable session. Old access-token-only files remain readable; they
cannot be refreshed without signing in again.

The new account transport uses `/api/v2/services` and `/api/v2/servers`. For encrypted
server responses, configure `response_key_id` and `response_key` from your authorized
private client research. Application secrets are intentionally absent from this
repository. A fresh ephemeral X25519 key is used for each server-list request;
the response is authenticated before its JSON is parsed. If no response key is
configured, only a server that explicitly returns a plaintext v2 list can be used.
Once encryption is requested, a plaintext response fails instead of downgrading.

Servers may also enforce request-context or device-header policies. This service
accepts explicit wire-format values but does not synthesize a native client's
environment report. Missing required settings produce upstream errors; offline
tests do not establish whether a particular deployment requires these headers.

Only v2 `shadowsocks` nodes representable by the existing standard SS generator are
exported. Mixed accounts keep their Shadowsocks nodes and omit other protocols,
including MonoLite and Papaya. Each exported Shadowsocks node must pass validation
for its connection fields, authentication options, and UDP settings. An account
needs at least one supported Shadowsocks node to generate a subscription. SS2022
requires a single base64 PSK of the method-specific size.

Account login remains the main-account `/oauth/token` flow. Native sub-user login
at `/oauth/sub-user/token` is not implemented. Template acquisition continues to
use the existing `update.json` manifest or an explicit compatible snapshot. When
the manifest's template list omits `Clash_ss`, the service downloads the official
asset from its known URL and verifies it against a pinned size and SHA-256.
The native client's `update.signed.json` app-update mechanism is not a replacement
for the project's existing template download/verification contract.

Refreshes are serialized across threads within the documented single application
worker. Refreshed credentials are persisted before the protected request proceeds.
Do not run multiple processes/workers against the same token file: cross-process
refresh coordination is not implemented. Revoked/forbidden sessions require a new
browser login; a rejected refresh is never retried automatically.
Confirmed revocation and rejected refreshes atomically replace the token file with
a re-login marker, so later requests and process restarts cannot reuse rejected
credentials. A successful browser login replaces that marker with the new session.

When enabled, Tailscale establishes its own underlying control/DERP/STUN and
peer connections directly; the client network must permit them. No `dialer-proxy`
is emitted: mihomo's proxy-backed UDP listener can fail before authorization
([upstream #3142](https://github.com/MetaCubeX/mihomo/issues/3142)). Public proxy
traffic still uses the manually selected MonoCloud node. Existing IP-based bootstrap DNS is preserved; when absent, `223.5.5.5` and
`119.29.29.29` are supplied. Hostname-dependent bootstrap settings are rejected.
Independent bootstrap DNS resolves proxy nodes. Tailnet IPv4/IPv6
and `*.ts.net` FQDNs route to Tailscale before the official LAN rules; Tailnet
DNS uses the outbound's own resolver. Short MagicDNS names without the Tailnet
suffix are not configured. Subnet routes require both a client configuration
entry and the corresponding Tailnet advertisement/authorization.

First-time client authorization, plan/node selection, subscription updates and
the optional Tailscale setup are documented in the management page's
**导入客户端 → Clash Mi**. Preserve each client's Tailscale state across
restarts and refreshes. Generated subscriptions contain node passwords and any
configured auth key; store and transfer them privately.

Docker, direct execution, and systemd are deployment choices. They can use the
same installed application entry point; no deployment method or fixed machine
path is required by the project. Optional [Docker Compose startup](docs/deployment.md#docker-compose)
is provided with a non-root image and persistent data volume. See [deployment](docs/deployment.md) for
management password setup, LAN addresses, HTTPS/reverse proxies and persistence.

## Development and checks

```sh
uv sync --locked
uv run monocloud-subscription --config .local/config.toml check
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv build
```

The `check` command validates configuration without writes, account requests or
starting a server; configuration errors exit with status 2.

To apply formatting, run `uv run ruff format .`. Commit `uv.lock` when changing
dependencies so subsequent installs can use `uv sync --locked`.

The package lives in `src/monocloud_subscription/`; behavioral tests live in
`tests/`. HTTP integration tests bind a temporary port on `127.0.0.1` and use fake
data; they require loopback socket access, not an external account. Build artifacts
are written to ignored `dist/`. Only application source
and declared package metadata belong in distributions; local configuration and
private research must remain excluded.

The subscription web layer uses the generator's Python API;
no account or generation CLI workflow is added:

```python
from pathlib import Path
import httpx
from monocloud_subscription.config import load_config
from monocloud_subscription.subscription import generate_subscription

config = load_config(Path(".local/config.toml"))
with httpx.Client() as http:
    subscription_yaml = generate_subscription(config, http)
# Contains credentials: pass privately to the serving layer; do not print/log it.
```

Generation loads the saved browser-login token, fetches all available Shadowsocks
nodes, downloads the official `Clash_ss` template from its update manifest, and
checks its size and SHA-256 before parsing. Manifest and asset redirects are
rejected, including HTTPS-to-HTTP redirects. Unexpected top-level template options
and non-rule routing modes are rejected rather than copied into the client. It preserves the official rule order
and provides manual `Proxy → plan → node` selection. Each nonempty service has
its own group; equal display names remain separate, and every available node is
included under its own service. Name collisions are
renamed deterministically; automatic switching is not enabled. Failure raises a
sanitized `ValueError` without writing output. The asset host must be reachable
from the deployment; HTTP 403/network failures are reported without silently
substituting another policy. If the asset host presents an automated-client challenge, `template_dir` can
explicitly select an operator-provided official snapshot. This is not a fallback:
it performs no download, trusts the operator's snapshot provenance, and keeps using
it until the operator replaces it. Do not mistake an old snapshot for a fresh
upstream check. Scheduled refresh and last-good publication belong to #5. See [verification details](docs/clash-verification.md) for device limits.
