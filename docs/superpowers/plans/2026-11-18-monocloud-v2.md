# MonoCloud 1.5 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Track results below.

**Goal:** Make the subscription service consume MonoCloud 1.5 authentication and node data.
**Architecture:** Extend the API client and private token store; keep the generator and URL store stable.
**Tech Stack:** Python 3.12+, httpx, cryptography, existing FastAPI/PyYAML.
**Spec:** ../specs/2026-11-18-monocloud-v2-design.md

## Global Constraints

- Use synthetic credentials; do not publish application secrets or account responses.
- No remote service or desktop changes. The requested repository destination is read-only in this session.
- Keep legacy APIs behind an explicit setting; fail closed on unsupported data.

## Review Focus

- Tampered ciphertext, wrong key ID or plaintext after requesting encryption must fail.
- Concurrent requests must not spend a rotating refresh token twice.
- Revoked/forbidden sessions and rejected refreshes must not create retry loops.
- Legacy token files must remain readable; browser responses must not contain credentials.
- Unsupported protocols/auth options must not generate plausible but unusable subscriptions.

### Task 1: API v2 and encrypted nodes

Files: monocloud.py, server_list.py, config.py, tests/test_v2.py, pyproject.toml, uv.lock.
Interfaces: ServerListCipher.request_headers()/decode(); MonoCloudSettings.api_version;
existing fetch_plans/fetch_nodes/fetch_all_nodes return Plan/Node.
- [x] Add failing v2 request, field mapping and cryptographic tamper/downgrade tests.
- [x] Implement the encrypted transport and strict v2 mapping; run API and generator tests.

### Task 2: Refreshable account state

Files: tokens.py, monocloud.py, subscription.py, web.py, tests/test_v2.py, tests/test_tokens.py.
Interfaces: Session, TokenStore.load_session/save_session/locked; login_session.
- [x] Add failing legacy-load, expiry, rotation, revocation and concurrent-refresh tests.
- [x] Implement serialized refresh, atomic persistence and web/subscription integration.
- [x] Run focused tests and the full suite; distinguish sandbox/dependency failures.

### Task 3: Release documentation and review

Files: README.md, config.example.toml, deploy/config.example.toml, docs/clash-verification.md.
- [x] Document private settings, migration, protocol limits and offline/live verification scope.
- [x] Review the final diff, verify lock graph and syntax, produce a patch for the upstream commit.
- [x] Record exact successful checks and environment-blocked checks before reporting completion.
