# MonoCloud to Subscription Link

## Purpose

Generate client subscriptions from MonoCloud nodes and official routing rules,
with optional Tailscale configuration for access to a Tailnet. The planned targets are
Clash/mihomo (Clash Mi first), sing-box MT, and Surge.

The subscription service will generate and serve configuration. The client device
will handle proxy traffic and, when enabled, Tailscale connections directly.
Subscriptions can be used with MonoCloud alone, without configuring or authorizing
Tailscale. Tailscale-specific routes and DNS settings are included only when enabled.

**Current status:** project initialization only. The installed command can check
local configuration and then exit. Node retrieval, login, subscription generation,
Tailscale integration, and HTTP serving are not implemented yet.

## Requirements and installation

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency and
  environment management.

From the repository root:

```sh
uv sync --locked
uv run monocloud-subscription --help
```

uv creates a project-specific `.venv/`. The application currently has no runtime
dependencies outside the Python standard library. Ruff is a development dependency.

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

## Configuration and private data

Configuration uses TOML. Supply its path explicitly with `--config`.

| Setting | Required | Meaning |
| --- | --- | --- |
| `data_dir` | Yes | Nonempty path reserved for runtime data. Relative paths resolve against the configuration file's directory. |

With `.local/config.toml` and `data_dir = "data"`, the runtime data location is
`.local/data/`, regardless of the process working directory. Absolute paths are
also supported. Use an absolute configuration path when invoking the installed
command from another directory.

Keep private research, personal configuration, future credentials, and runtime
data in `.local/`, which Git ignores. An external private directory is equally
valid. Credential storage is not implemented yet, so the example contains no
login or token fields. Do not put real credentials or generated subscriptions
in tracked files or issue reports.

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
`tests/`. Build artifacts are written to ignored `dist/`. Only application source
and declared package metadata belong in distributions; local configuration and
private research must remain excluded.

