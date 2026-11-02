# MonoCloud Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement confirmed MonoCloud API calls, shared nodes, private token storage, and browser account access for issue #2.

**Architecture:** A small httpx client and local JSON token store, used by the login page described in the login-page plan. CLI commands only start the service and check configuration; no account-refresh machinery.

**Tech Stack:** Python, uv, httpx, unittest, Ruff.

**Spec:** `docs/superpowers/specs/2026-11-02-monocloud-integration-design.md`

## Global Constraints

- The existing MonoCloud installation is not changed. The user later authorized read-only inspection and existing-session GET queries.
- Never echo passwords, tokens, node credentials, or remote error bodies.
- Use confirmed service/node interfaces. Real browser login and token reuse are now verified.

## Review Focus

- Expired/rejected authentication produces actionable errors and a single request.
- Unexpected status/body/schema failures never expose response contents.
- Failed login or token write retains the previously saved token.
- Config-relative token paths work independently of the working directory.
- Node credentials are excluded from representations and browser responses.

## Task 1: Token storage

**Files:** `src/monocloud_subscription/tokens.py`, `tests/test_tokens.py`.
**Interfaces:** `TokenStore(path: Path).load() -> str`, `.save(token: str) -> None`.

- [x] Write and run failing tests for round trips, missing/corrupt storage, owner-only permissions, and invalid writes retaining old data.
- [x] Implement simple private atomic storage; run tests to green.

## Task 2: API calls and shared node model

**Files:** `src/monocloud_subscription/monocloud.py`, `tests/test_monocloud.py`, `pyproject.toml`, `uv.lock`.
**Interfaces:** `MonoCloudClient(settings, http).login(...) -> str`, `.fetch_nodes(token, service_id) -> list[Node]`. Both Plan and Node expose service_id.

- [x] Add httpx and deterministic MockTransport tests for exact request headers/forms, node mapping, disabled nodes, malformed responses, sanitized errors, and no authentication retry.
- [x] Run tests red, implement client/model, then run full suite green.

## Task 3: Service entry point and documentation

**Files:** `config.py`, `cli.py`, `config.example.toml`, `README.md`, related tests.
**Interfaces:** `main(argv)` exposes only `check` and `serve`; browser account interaction uses `create_app(config)`.

- [x] Test config defaults/overrides, missing settings, authentication failures, and secret-safe API behavior.
- [x] Use browser login instead of CLI account prompts; preserve read-only `check`, service startup, and help behavior.
- [x] Keep README's five sections, document verified versus pending API behavior, and update issue #2 progress in English.
- [x] Run full suite, Ruff, build, and an independent code/security review. Keep #2 open until plan discovery and live verification are actually complete.


## Verification and outstanding evidence

- 30 behavioral tests passed on Python 3.14.4; Ruff lint and formatting passed.
- Both wheel and source distributions built successfully.
- Independent code/security review found no important or critical findings.
- The user subsequently authorized remote read-only research. Existing-session GET queries confirmed /api/service and /api/shadowsocks/{service_id}, response arrays/field types, and request headers.
- Added Plan, fetch_plans, and fetch_all_nodes. Outer service id is used rather than product plan_id. These API methods remain available internally after removing account CLI commands.
- The suite reached 33 passing tests after service discovery; incremental independent review passed.
- The original backend suite passed real loopback HTTP login/save/reuse/discovery and rejected-token checks. Obsolete CLI account tests were later removed after browser login became the sole account interaction; equivalent API and web coverage remains.
- A proposed raw-response relay to the local process was rejected by automatic approval and was not executed. The temporary relay script was removed; no raw responses or live tokens were transferred locally.
- Live acceptance is now complete: the user submitted real browser login, and the project successfully reused the returned token for read-only service/node discovery. No account or node secrets are recorded here.
- Local integration tests use fabricated credentials. No remote configuration writes, token refreshes, or proxy-node connections were performed.
- Mark PR #8 ready for review; keep issue #2 open until merge.
