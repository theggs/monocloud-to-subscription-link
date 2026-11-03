# Management Interface Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the management page with the approved four-step guided flow (#11).

**Architecture:** Two small API additions feed a rewritten native HTML/CSS/JS page.
The page derives exactly one current step from `/api/status?verify=true` and
`/api/subscription`. The Clash Mi guide stays a separate bundled resource that
the server embeds.

**Tech Stack:** Python 3 / FastAPI, unittest + httpx ASGI tests, vanilla JS/CSS.

**Spec:** `docs/superpowers/specs/2026-11-03-management-redesign-design.md`
(mockup: `docs/design/2026-11-03-management-redesign-mockup.html`)

## Global Constraints

- The CSP is `default-src 'self'; script-src 'self'; style-src 'self'`. No
  inline `style=` or `<script>`. Use classes only.
- All asset/API URLs stay relative (`assets/…`, `api/…`) so `/mono/` prefix
  mounts work.
- No client/kernel name in the title, the next-step line, ①, ②, or the
  ③/④ step titles. "mihomo"/"Clash Mi" appear only in the mihomo link row
  and the Clash Mi guide.
- No "手机"/"Safari" assumptions. Device names appear only in the
  verification note.
- Clash Mi guide text comes from the existing `guides/clash-mi.html`. Only
  control references and device wording change.
- Never claim import success, Tailnet connectivity or generation success.
- Tests use constructed data only.

## Review Focus

- A saved token whose verification is "unavailable" must not render as
  "已验证". It renders a warn state with "重新验证".
- `tailscale_enabled` comes from config while `tailscale_choice_saved` is false:
  ② shows the config default as the pre-selected choice and requires "确认".
- A long URL or long plan names must not create horizontal overflow at 320px.
- A failed save must keep the draft and the "未保存" state, and the link step
  must say it serves the saved contents.
- An API fetch failure, such as a network error or a 401 Basic-auth expiry,
  must show a retry, not a blank page.

---

### Task 1: API — plan names and saved-choice flag

**Files:**
- Modify: `src/monocloud_subscription/web.py` (status, subscription_details)
- Test: `tests/test_web.py`

**Interfaces:**
- Produces: `/api/status?verify=true` returns `plan_names: list[str]` (`[]`
  unless connected). `/api/subscription` (GET and POST) returns
  `tailscale_choice_saved: bool`.

- [ ] Step 1: Replace `test_verified_saved_session_reports_service_count_without_account_data`
  with `test_verified_saved_session_reports_plan_names_without_token`. Assert
  `plan_count == 2` and `plan_names == ["private-plan-name", "Other"]`, and that
  "constructed-token" is not in the response. In
  `test_signed_out_verified_status_does_not_contact_upstream`, assert
  `plan_names == []`.
- [ ] Step 2: Add `test_choice_saved_flag_tracks_first_save`. A fresh GET gives
  `tailscale_choice_saved is False`. After POST `{"tailscale_enabled": false}`,
  both the POST response and the GET give `True`.
- [ ] Step 3: Run `uv run python -m unittest tests.test_web -v`. Expect FAIL on
  the new assertions.
- [ ] Step 4: Implement. Add `plan_names=[plan.name for plan in plans]` to the
  status result. Add `"tailscale_choice_saved": state.tailscale_enabled is not None`
  in `subscription_details`.
- [ ] Step 5: Run the same command. Expect all to pass. Commit with
  `feat: expose plan names and saved Tailscale choice to management page`.

### Task 2: Clash Mi guide resource

**Files:**
- Modify: `src/monocloud_subscription/static/guides/clash-mi.html` (rewrite)
- Test: `tests/test_web.py` (`test_page_embeds_clash_mi_guide_with_optional_overlay`)

**Interfaces:**
- Produces: `<details class="client" id="guide-clash-mi">`, with a summary that
  contains the name, the format pill and the key action. Inside it,
  `<details class="ext" id="guide-clash-mi-tailscale">`. The JS sets `open` and
  fills `<span data-plan-names>` inside the plan/node step.

- [ ] Step 1: Update the test.
  - It asserts that `id="guide-clash-mi"`, `id="guide-clash-mi-tailscale"`,
    "可选：增加 Tailscale 能力" and "在“核心设置 → 日志等级”选择 info" are present.
  - It asserts that "手机", "Safari", "若未自动出现授权页",
    `id="guide-surge"` and `id="guide-sing-box"` are absent.
- [ ] Step 2: Run the test and expect it to fail.
- [ ] Step 3: Rewrite the file with the spec's ④ structure. Copy the text
  verbatim from the mockup's `clientStep` (taken from the original guide), with
  `${planTxt}` replaced by `<span data-plan-names></span>`.
- [ ] Step 4: The test passes. Commit with `feat: restructure Clash Mi guide as a client row`.

### Task 3: Page markup, styles and behavior

**Files:**
- Modify: `src/monocloud_subscription/static/login.html`, `login.css`, `login.js`
  (rewrite)
- Test: `tests/test_web.py` (page tests)

**Interfaces:**
- Consumes: the Task 1 API fields and the Task 2 guide IDs.
- Element IDs the JS relies on:
  - `next-step`
  - `step-account`, `step-content`, `step-link`, `step-client`
  - `login-form`, `email`, `password`, `password-toggle`
  - `content-form` with radios `name="content"`, values `proxy` and `tailscale`
  - `subscription-url`, `copy-subscription`, `download-subscription`

- [ ] Step 1: Update the page tests.
  - They keep the asset, prefix, `name="password"` and no-secret checks.
  - They assert the four step IDs, the heading "设置你的代理订阅", and that
    "Surge、sing-box 格式尚未支持" is present.
  - They assert "admin</span>" is absent.
  - The no-client-name check applies to the markup outside `#step-link` and
    `#guide-clash-mi`.
- [ ] Step 2: Run the tests and expect them to fail.
- [ ] Step 3: Write `login.html`. Use the static skeleton of the four steps from
  the spec, with hidden subsections toggled by `hidden`.
- [ ] Step 4: Write `login.css`. Port the mockup's `.A` rules (tokens, steps,
  pills, segmented control, URL row, client row, alerts, focus, the ≤600px
  container rules). Do not port the mockup chrome rules.
- [ ] Step 5: Write `login.js`.
  - Load `api/status?verify=true` and `api/subscription`, then `render()` from
    one state object whose fields mirror the mockup's `model()`.
  - Keep the current login error-code map and its password-clearing `finally`.
  - Copy uses the clipboard API with a select/execCommand fallback. On total
    failure, expand and select the URL text and advance to ④.
  - Download advances to ④.
  - The loopback check covers `localhost`, `127.0.0.1` and `[::1]`.
- [ ] Step 6: Run `uv run python -m unittest discover -s tests`. Everything
  passes. Commit with `feat: redesign management page as guided four-step flow`.

### Task 4: Documentation wording

**Files:**
- Modify: `README.md` (≈67, ≈128-129), `docs/deployment.md` (≈40, 145, 152, 177)

- [ ] Step 1: Replace phone-only wording with "device/other devices", and the
  guide path with **导入客户端 → Clash Mi**. Keep the management-password
  instructions.
- [ ] Step 2: Commit with `docs: describe subscription use on any device`.

### Task 5: Browser QA

- [ ] Step 1: Serve with constructed data.
  - Use a temp config with fake OAuth, `MONOCLOUD_WEB_PASSWORD`, and a
    `httpx.MockTransport` app (a small script in the scratchpad) that switches
    between account states.
  - Verify desktop and 390px for: signed out, connected (first-time and
    returning), expired, expired without OAuth, unavailable, and a subscription
    read error.
- [ ] Step 2: Check:
  - One `[aria-current=step]` and no overflow.
  - On a returning user, the copy button's bottom edge is above the viewport
    height.
  - Keyboard tab order, and the copy/download/save/undo/relogin flows.
  - A `/mono/` prefix through a strip-prefix proxy.
