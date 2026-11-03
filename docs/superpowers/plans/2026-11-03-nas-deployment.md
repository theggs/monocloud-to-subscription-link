# NAS Compose deployment plan

**Goal:** Run the current application on the user's NAS under `~/docker/`,
with private configuration and persistent state kept outside Git.

**Approach:** Reuse the existing image, application entry point and Compose
service. Add optional host-directory storage and UID/GID settings, keeping
the named-volume defaults. Use a private `.env` for deployment settings and
the existing service environment file for the management password.

- [x] Verify Docker/Compose, target architecture, port availability and upstream access.
- [x] Add generic Compose settings and document NAS ownership, backup and upgrades.
- [x] Build for the target and verify both named-volume and host-directory modes.
- [x] Transfer only tracked application files plus explicitly selected private
  configuration, token/state and an official template snapshot if needed.
- [x] Start the NAS service; check auth, account status, complete subscription
  generation, preserved key/settings and recreation. Record deployment revision
  privately and push generic repository improvements.

No daemon configuration, global firewall changes, privileged containers or
server-side Tailscale daemon are required.

**Verification:** 103 unit tests, Ruff checks and both local storage smoke modes
passed. An amd64 image was cross-built on the workstation and loaded over SSH
because direct NAS downloads were slow. The NAS bind-data smoke check passed
on Docker 24.0.2 / Compose 2.20.1. Live checks passed before and after recreation,
including authenticated account verification and full subscription download.
The user explicitly authorized transfer of the selected existing app credentials
and state; none were printed or committed. Runtime image/source revision: 47d6409.
