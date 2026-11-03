# Container support implementation plan

**Goal:** Offer optional container deployment without changing application behavior.

**Architecture:** Build the locked Python application with uv; copy its installed
environment into a non-root runtime image. Mount private TOML read-only and persist
the entire runtime directory in a named volume. Compose is a convenience alongside
direct execution, not a required architecture.

**Scope:** Dockerfile, allowlisted build context, Compose, a container TOML example,
and deployment instructions. No server-side Tailscale daemon or account CLI.

- [x] Build the image with production-only locked dependencies; inspect its user,
  bundled static guide, and absence of private workspace files.
- [x] Validate Compose with fake credentials and configuration. Start on a separate
  local port; check management authentication and non-root volume writes.
- [x] Recreate the container using the same volume; verify the URL credential and
  saved settings survive, and verify SIGTERM shuts down cleanly.
- [x] Document startup, LAN publishing, private configuration, persistence, optional
  template snapshots and shutdown; keep README Quick start concise.

Verified on local Docker (Linux arm64): image build and disposable Compose smoke
check passed, including exit code 0 on SIGTERM. Existing 100 unit tests and Ruff
checks passed. No real MonoCloud credentials or existing service state were used.
