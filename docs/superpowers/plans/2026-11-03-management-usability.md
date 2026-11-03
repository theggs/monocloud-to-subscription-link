# Management Usability Implementation Plan

**Goal:** Implement approved items 1, 2, 3 and 5 on the existing #4 branch.
**Architecture:** Pass service metadata through the renderer, extend optional
verified status, use native collapsible account UI and one bundled client guide.
**Stack:** Python/uv, FastAPI/httpx, HTML/CSS/JS, unittest, Playwright QA.
**Spec:** ../specs/2026-11-03-management-usability-design.md

## Constraints and review focus

All plans/nodes remain present and manually selectable. No private values in Git.
No new auth method, account CLI, policy classification or client format. Group and
node names share a collision namespace; duplicate plan names remain separate by
service ID. An upstream outage is not an expired login. Startup must never echo
the configured management password. Guide is basic access plus optional overlay.

## Tasks

- [x] Write failing grouping tests (membership, repeated names, reserved names,
  empty-service omission) and orchestration assertions; implement the optional
  plans argument and two-layer manual selection.
- [x] Write failing verified-status and startup-privacy tests; implement account
  verification states and explicit credential-source messages.
- [x] Rework the native account/subscription layout; embed a Clash Mi guide resource
  with base plus optional Tailscale steps; keep other client guides deferred.
- [x] Run constructed-data desktop/mobile UI QA, full tests, Ruff and build;
  verify both generated modes with the official core and actual service output.
- [x] Update README/PR evidence, restart the owned local service for review, and
  identify the additional phone hierarchy check without claiming it already passed.

Validation: 100 unittest tests passed; Ruff and build passed. Constructed browser
QA covered connected/relogin/signed-out/expired/unavailable states and mobile guide
layout. Both sanitized and actual HTTP two-mode configurations passed core checks;
actual plan/node membership matched API data. New phone hierarchy remains a distinct
user revalidation item, not an inherited acceptance claim.
