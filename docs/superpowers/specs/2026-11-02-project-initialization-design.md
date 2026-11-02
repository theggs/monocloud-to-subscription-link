# Project initialization

## Intent and scope

Build the foundation for MonoCloud subscription generation with optional Tailscale support.
Use Python and uv, with a packaged CLI and an explicit local configuration file.
The initial CLI checks TOML configuration and exits; subscription serving belongs
to issue #4. Clash/mihomo, sing-box, and Surge remain planned output targets.

## Decisions

- Python >=3.12, uv dependency management, and a `src/` package.
- No runtime dependencies for initialization. Use argparse and tomllib.
- Tailscale is optional. MonoCloud-only subscriptions require no Tailscale settings
  or authorization. Include Tailscale-specific routing and DNS only when enabled;
  verify both modes separately in each client generator. No Tailscale configuration
  fields are needed in this bootstrap, which does not generate subscriptions yet.
- Provide `monocloud-subscription --config PATH check` and `--help`.
- A required nonempty `data_dir` string is resolved relative to the config file,
  making it independent of the process working directory. Checking creates no files.
- Store private config, credentials, research, and runtime data under ignored
  `.local/` by convention; external paths are also supported.
- Report configuration errors without echoing file contents or parser details.
- Use unittest for configuration/CLI behavior, Ruff for lint and formatting.

## Approaches

Python + uv was accepted over Go. Deployment was explicitly separated from
architecture: direct execution, Docker, and systemd may all call the same entry
point later. No deployment method is required or implemented in this issue.

## Non-goals

No authentication, network requests, subscriptions, background server, plugin
framework, database, or deployment manifests. Do not add placeholders for future
components. Concrete configuration fields arrive with the features that use them.

## Documentation

README: purpose (including current status), requirements/installation, quick start,
configuration and private data, development checks. Track future work in issues.
All examples are generic and contain
no personal identities, machine paths, node credentials, or live deployment URLs.
