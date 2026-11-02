# Clash/mihomo Generator Implementation Plan

**Goal:** Generate complete official-policy subscriptions with optional Tailscale.
**Architecture:** Verified template fetch, pure structured renderer, thin saved-token orchestration.
**Tech stack:** Python 3.12, uv, httpx, PyYAML, unittest.
**Spec:** ../specs/2026-11-02-clash-generator-design.md

## Constraints

No personal values in Git. No account CLI, subscription HTTP/UI (#4), scheduled
refresh (#5), auto-switching or deployment scaffolding. Work in feature branch.

## Tasks

1. Template and renderer (`templates.py`, `clash.py`, `tests/test_clash.py`):
   - [x] Write failing tests for digest/size, malformed asset and placeholders,
     complete node inclusion, reserved/duplicate names, YAML-sensitive values,
     unchanged input and official rule order.
   - [x] Add PyYAML; implement verified fetch and structured rendering; run tests.
2. Local settings and orchestration (`config.py`, `subscription.py`, config tests):
   - [x] Fail tests for optional Tailscale, client state paths, subnet validation,
     secret-safe errors, API composition and failure propagation.
   - [x] Implement small settings dataclasses and saved-token orchestration.
3. Verification and docs:
   - [x] Run whole suite, Ruff and build. Generate both sanitized variants and
     run official mihomo v1.19.32 config checks; record commands/results.
   - [x] Update README/example and issue progress with unverified phone behavior.

## Review focus

Untrusted node aliases must remain data, never YAML/rule syntax. Template changes
must fail explicitly instead of leaving unresolved placeholders. Digest applies
to exact downloaded bytes. Tailscale DNS must not bootstrap through itself.
Generated state paths must not inherit the server's local absolute paths.

Validation: 70 tests passed; Ruff check/format, uv build and both sanitized
mihomo v1.19.32 checks passed. Real-node private outputs also passed core checks.
Clash Mi device acceptance is explicitly pending; issue remains open.
