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
is tested against a local HTTP server using constructed credentials. Read-only live
queries also confirmed the service/node response structures. Fresh OAuth login
against MonoCloud is pending. Subscription generation, Tailscale integration, and
HTTP serving are not implemented yet.

## Requirements and installation

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency and
  environment management.

From the repository root:

```sh
uv sync --locked
uv run monocloud-subscription --help
```

uv creates a project-specific `.venv/`. HTTP requests use httpx; Ruff is a
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

To use an existing access token, run this in an interactive terminal and paste
the token at the hidden prompt:

```sh
uv run monocloud-subscription --config .local/config.toml import-token
```

Alternatively, set the OAuth client credentials in your private configuration,
then log in. The email and password are requested interactively; the password is
not saved:

```sh
uv run monocloud-subscription --config .local/config.toml login
```

List Shadowsocks plans or discover all of their nodes:

```sh
uv run monocloud-subscription --config .local/config.toml plans
uv run monocloud-subscription --config .local/config.toml nodes
```

To query specific plans, use the service IDs shown by `plans`, replacing the example ID:

```sh
uv run monocloud-subscription --config .local/config.toml nodes --plan-id 123
```

Repeat `--plan-id` to query multiple plans. The identifier is the outer service
record's `id`, not `plan_id` or the nested `plan.id`. The node command reports only the total
number of available nodes; it does not print or save connection details, connect
to proxy nodes, or perform speed tests. Rejected authentication requires manual
login or token import; it does not trigger automatic login retries.

**API verification limits:** static client inspection confirms the password-grant
form and embedded OAuth client-credential source. Read-only GET requests using an
existing session confirmed `/api/service`, `/api/shadowsocks/{service_id}`, their
array responses, field types, and request identity. Tests use constructed data with
the confirmed structure, without real account or node values. Fresh login and the
project's transport against the real MonoCloud service remain unverified. Local
HTTP integration tests cover login, token persistence, and discovery. Configure OAuth client
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
| `monocloud.client_id`, `monocloud.client_secret` | For login | OAuth client credentials. Not needed to import and reuse an existing token. |

With `.local/config.toml` and `data_dir = "data"`, the runtime data location is
`.local/data/`, regardless of the process working directory. Absolute paths are
also supported. Use an absolute configuration path when invoking the installed
command from another directory.

Keep private research, personal configuration, future credentials, and runtime
data in `.local/`, which Git ignores. An external private directory is equally
valid. On POSIX systems new token files have owner-only permissions; token updates
replace the file atomically. Token import stores the supplied value without checking
it against the server. Login saves only the returned access token; passwords and raw
API responses are not persisted. Local configuration containing OAuth client secrets
should also be readable only by its owner. Do not put real credentials or generated
subscriptions in tracked files or issue reports.

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

