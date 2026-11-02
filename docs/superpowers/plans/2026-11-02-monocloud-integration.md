# MonoCloud Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement confirmed MonoCloud API calls, shared nodes, token storage, and CLI commands for issue #2.

**Architecture:** A small httpx client and local JSON token store, wired into the existing CLI. No server or account-refresh machinery.

**Tech Stack:** Python, uv, httpx, unittest, Ruff.

**Spec:** `docs/superpowers/specs/2026-11-02-monocloud-integration-design.md`

## Global Constraints

- The existing MonoCloud installation is not changed. The user later authorized read-only inspection and existing-session GET queries.
- Never echo passwords, tokens, node credentials, or remote error bodies.
- Use confirmed service/node interfaces; fresh OAuth login remains a separate unverified acceptance criterion.

## Review Focus

- Expired/rejected authentication produces actionable errors and a single request.
- Unexpected status/body/schema failures never expose response contents.
- Failed login or token write retains the previously saved token.
- Config-relative token paths work independently of the working directory.
- Node credentials are excluded from representations and CLI output.

## Task 1: Token storage

**Files:** `src/monocloud_subscription/tokens.py`, `tests/test_tokens.py`.
**Interfaces:** `TokenStore(path: Path).load() -> str`, `.save(token: str) -> None`.

- [x] Write and run failing tests for round trips, missing/corrupt storage, owner-only permissions, and invalid writes retaining old data.
- [x] Implement simple private atomic storage; run tests to green.

## Task 2: API calls and shared node model

**Files:** `src/monocloud_subscription/monocloud.py`, `tests/test_monocloud.py`, `pyproject.toml`, `uv.lock`.
**Interfaces:** `MonoCloudClient(settings, http).login(...) -> str`, `.fetch_nodes(token, plan_id) -> list[Node]`.

- [x] Add httpx and deterministic MockTransport tests for exact request headers/forms, node mapping, disabled nodes, malformed responses, sanitized errors, and no authentication retry.
- [x] Run tests red, implement client/model, then run full suite green.

## Task 3: CLI and documentation

**Files:** `config.py`, `cli.py`, `config.example.toml`, `README.md`, related tests.
**Interfaces:** existing `main(argv)`; new `import-token`, `login`, `nodes --plan-id ID` commands.

- [x] Test config defaults/overrides, missing settings, noninteractive node errors, and secret-free command output before implementation.
- [x] Implement prompts and command wiring; preserve read-only `check` and help behavior.
- [x] Keep README's five sections, document verified versus pending API behavior, and update issue #2 progress in English.
- [x] Run full suite, Ruff, build, and an independent code/security review. Keep #2 open until plan discovery and live verification are actually complete.


## Verification and outstanding evidence

- 30 behavioral tests passed on Python 3.14.4; Ruff lint and formatting passed.
- Both wheel and source distributions built successfully.
- Independent code/security review found no important or critical findings.
- The user subsequently authorized remote read-only research. Existing-session GET queries confirmed /api/service and /api/shadowsocks/{service_id}, response arrays/field types, and request headers.
- Added Plan, fetch_plans, fetch_all_nodes, the plans CLI command, and default node discovery. Outer service id is used rather than product plan_id.
- The suite reached 33 passing tests after service discovery; incremental independent review passed.
- The final suite has 38 passing tests, including real loopback HTTP login/save/reuse/discovery, rejected-token handling, and successful CLI import/plans/nodes. Lint, formatting, and distribution builds passed.
- A proposed raw-response relay to the local process was rejected by automatic approval and was not executed. The temporary relay script was removed; no raw responses or live tokens were transferred locally.
- Pending: fresh OAuth login and project HTTP transport against the actual MonoCloud service. Local integration tests use fabricated credentials. No real login, refresh, remote configuration write, service restart, or node connection was performed.
- Issue #2 remains open pending production login acceptance; submit the verified implementation on codex/monocloud-integration for draft review.
