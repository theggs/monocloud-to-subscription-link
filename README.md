# MonoCloud to Subscription Link

## Purpose

Generate client subscriptions from MonoCloud nodes and official routing rules,
with optional Tailscale configuration for access to a Tailnet. The planned targets are
Clash/mihomo (Clash Mi first), sing-box MT, and Surge.

The subscription service will generate and serve configuration. The client device
will handle proxy traffic and, when enabled, Tailscale connections directly.
Subscriptions can be used with MonoCloud alone, without configuring or authorizing
Tailscale. Tailscale-specific routes and DNS settings are included only when enabled.

**Current status:** configuration checks, local token storage, password-grant login,
service discovery, and node retrieval are implemented. The complete account workflow
is tested against a local HTTP server using constructed credentials. Browser login
and reuse of its saved token for service/node discovery have also been verified
against MonoCloud. A browser login page is available. Subscription
generation for Clash/mihomo is available as a Python API, with optional Tailscale.
Subscription downloads are not implemented yet. Clash Mi device verification
remains pending; see [generator verification](docs/clash-verification.md).

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
serve the login page; PyYAML parses and serializes Clash configuration. Ruff is a
development dependency.

## Quick start

Copy the generic example into the ignored local directory:

```sh
mkdir -p .local
cp config.example.toml .local/config.toml
uv run monocloud-subscription --config .local/config.toml check
```

The command prints `Configuration OK` and the configured data directory, then
exits successfully. It does not create the directory, write credentials, contact
MonoCloud, or start a server. A configuration error exits with status 2.

For browser login, configure the private OAuth client parameters described below,
then start the login page:

```sh
uv run monocloud-subscription --config .local/config.toml serve
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080), enter your account email and
password, and submit the form. The page shows pending/success/error states and
whether a token is already saved. It does not display tokens or OAuth client
secrets. Failed login preserves the previous token. The password is cleared from
the form after each attempt and is not stored by the application.

The server defaults to loopback. Use `--host` and `--port` to select a listen
address. Binding beyond loopback requires a `MONOCLOUD_WEB_PASSWORD` environment
variable; browsers then prompt for username `admin` and that management password.
This password controls access to the login page and is distinct from your MonoCloud
account password. Supply it through your deployment's private environment, not
committed configuration or command-line arguments. Remote HTTP transmits both
account and management credentials without encryption, including over LAN/Wi-Fi.
The service prints its listen URL and warns when binding beyond loopback. Use
HTTPS for remote browser access; TLS termination remains a deployment choice.

When using an HTTPS reverse proxy, forward the original `Host` and set
`X-Forwarded-Proto`. Uvicorn trusts forwarded headers from loopback by default;
if the proxy runs elsewhere, set `FORWARDED_ALLOW_IPS` to its specific trusted
address. Do not trust arbitrary client-supplied forwarded headers. The Origin
check still requires matching scheme, hostname and effective port. Request access
logs are disabled. This page implements only account login for issue #2.

Account interaction is available through the browser page. The command-line
entry point is limited to starting the service and checking configuration.

**API verification limits:** static client inspection confirms the password-grant
form and embedded OAuth client-credential source. Read-only GET requests using an
existing session confirmed `/api/service`, `/api/shadowsocks/{service_id}`, their
array responses, field types, and request identity. Tests use constructed data with
the confirmed structure, without real account or node values. The user completed
browser login, and the project reused its saved token for read-only service/node
queries against the real API. Local HTTP integration tests also cover login,
token persistence, discovery, and authentication failures. Configure OAuth client
credentials privately; no client secrets are bundled.

## Configuration and private data

Configuration uses TOML. Supply its path explicitly with `--config`.

| Setting | Required | Meaning |
| --- | --- | --- |
| `data_dir` | Yes | Nonempty path reserved for runtime data. Relative paths resolve against the configuration file's directory. |
| `token_file` | No | Token JSON path; defaults to `data_dir/token.json`. An explicit relative path resolves against the configuration file. |
| `monocloud.base_url` | No | HTTPS API root; defaults to the researched MonoCloud API. |
| `monocloud.user_agent` | No | User-Agent header, default `MonocloudGO-1.0.1` from the verified client. |
| `monocloud.client_version` | No | X-Client-Version header, default `1.0.1`; an empty string omits it. |
| `monocloud.client_id`, `monocloud.client_secret` | For login | OAuth client credentials. Not required to reuse a saved token. |
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
data in `.local/`, which Git ignores. An external private directory is equally
valid. On POSIX systems new token files have owner-only permissions; token updates
replace the file atomically. Existing directory permissions are left unchanged;
deployers should restrict private configuration and data directories. Atomic
replacement is not a power-loss durability guarantee. Browser login saves only the returned access token; passwords and raw
API responses are not persisted. Local configuration containing OAuth client secrets
should also be readable only by its owner. Do not put real credentials or generated
subscriptions in tracked files or issue reports.

When enabled, Tailscale uses the selected MonoCloud node for control/DERP
connections. Existing IP-based bootstrap DNS is preserved; when absent, `223.5.5.5` and
`119.29.29.29` are supplied. Hostname-dependent bootstrap settings are rejected.
Independent bootstrap DNS resolves proxy nodes. Tailnet IPv4/IPv6
and `*.ts.net` FQDNs route to Tailscale before the official LAN rules; Tailnet
DNS uses the outbound's own resolver. Short MagicDNS names without the Tailnet
suffix are not configured. Subnet routes require both a client configuration
entry and the corresponding Tailnet advertisement/authorization.

Authorize the client using the core's login URL if the client exposes it, or
supply a private auth key. Keep the same non-ephemeral device's client-side state
directory across restarts and subscription refreshes; preserve it in the client
sandbox or its deployment's persistent storage. Different devices should have
separate state. A generated subscription contains node passwords and, when set,
the Tailscale auth key: store and transfer it privately.

Docker, direct execution, and systemd are deployment choices. They can use the
same installed application entry point; no deployment method or fixed machine
path is required by the project.

## Development and checks

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv build
```

To apply formatting, run `uv run ruff format .`. Commit `uv.lock` when changing
dependencies so subsequent installs can use `uv sync --locked`.

The package lives in `src/monocloud_subscription/`; behavioral tests live in
`tests/`. HTTP integration tests bind a temporary port on `127.0.0.1` and use fake
data; they require loopback socket access, not an external account. Build artifacts
are written to ignored `dist/`. Only application source
and declared package metadata belong in distributions; local configuration and
private research must remain excluded.

The generator's Python API is intended for the subscription web layer in #4;
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
and provides one manual `Proxy` group containing every node. Name collisions are
renamed deterministically; automatic switching is not enabled. Failure raises a
sanitized `ValueError` without writing output. The asset host must be reachable
from the deployment; HTTP 403/network failures are reported without silently
substituting another policy. Scheduled refresh and last-good publication belong
to #5. See [verification details](docs/clash-verification.md) for device limits.
