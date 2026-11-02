# Protected Subscription Service Implementation Plan

**Goal:** Provide protected Clash URLs and a minimal browser workflow for #4.
**Architecture:** Existing FastAPI app plus small persisted subscription state;
existing generator and explicit verified local-template source.
**Spec:** ../specs/2026-11-02-subscription-service-design.md
**Stack:** Python/uv, FastAPI/httpx, native HTML/CSS/JS, unittest.

## Constraints

No personal values in tracked files. No new account CLI, refresh scheduler,
last-good publishing, dashboard or deployment framework. Use feature branch.

## Tasks

- [x] State/config/template source: write failing tests; implement persisted random
  key/toggle, optional private key override, server options and verified local
  official snapshot. Ensure no read-only check writes and no state corruption reset.
- [x] Protected HTTP workflow: fail tests for missing/wrong keys, separate management
  auth, successful GET/HEAD YAML, privacy-safe failures and same-origin toggle;
  implement using existing generator; run full tests.
- [x] Browser card: preserve existing design, expose copy/download and saved toggle;
  fake browser desktop/mobile QA; no personal credential replay.
- [x] Docs/build/security: record transport/state/URL semantics, run Ruff/build/tests,
  ensure private state and configs excluded; prepare actual service for phone tests.
- [ ] Record actual phone results as they occur; do not substitute a core parse.

## Review focus

Unknown credentials must never trigger upstream requests. URL management must
remain protected while native subscription downloads avoid Basic auth. Existing
URLs and toggles survive restart. Upstream/storage errors never echo secrets.
Official snapshot validation must not bypass digest checks or invent fresh data.

Validation: 90 tests pass; Ruff and build passed. Fake-data browser copy, download,
save/reload and 390px layout checked. Actual HTTP downloads in both modes pass
mihomo v1.19.32 using the explicit verified official snapshot. Phone results pending.
