# Login Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add the browser login flow requested for issue #2, without other feature pages.

**Architecture:** FastAPI serves packaged static files and two small account endpoints using the existing client/store. CLI serve starts Uvicorn.

**Tech Stack:** Python + uv, FastAPI, Uvicorn, native HTML/CSS/JavaScript.

**Spec:** `docs/superpowers/specs/2026-11-02-login-page-design.md`

## Global Constraints

- No Tailscale/subscription/update UI or API.
- OAuth application secrets remain in private configuration; save only access tokens.
- User requested continuous implementation; execute the agreed scope without further design handoffs.

## Review Focus

- Validation errors must never echo submitted passwords.
- Failed upstream login or storage must preserve existing token data.
- Saved credentials do not imply current remote token validity.
- LAN binding requires a management password; cross-origin mutations fail.
- Static resources must work from an installed wheel without source checkout access.

## Tasks

- [x] Add backend endpoint tests, observe missing implementation failures, then implement web app and CLI serve.
- [x] Build a responsive login-only page and accessible form states; integrate endpoints and clear sensitive form values.
- [x] Verify all tests, real-browser interactions, packaging and installed assets, and code/security review. Update README (five sections), issue #2 and draft PR #8 in English, then commit/push on the existing issue branch.


## Verification

- 49 tests passed, including the login-page API and CLI serve behavior; lint, formatting, source/wheel builds passed.
- Real browser verified constructed-account success/failure, password clearing/hiding, and mobile layout without horizontal overflow.
- A clean wheel installation served HTML, CSS, JavaScript, and the icon without source checkout access.
- Independent code/security review found no important actionable defects.
- The actual login page is available locally; no real MonoCloud login was submitted by the agent.
- The user completed real browser login. Subsequent project GET requests using the saved token verified service discovery, node retrieval, and required fields without printing or persisting raw node responses.
- SOCKS proxy regression coverage brings the full suite to 50 passing tests. Real login acceptance is complete; PR #8 can leave draft status.
