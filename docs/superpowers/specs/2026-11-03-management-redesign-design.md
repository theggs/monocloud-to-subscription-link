# Management interface redesign (#11)

Approved through several review rounds with the user and two codex reviews. The
clickable reference is
[`docs/design/2026-11-03-management-redesign-mockup.html`](../../design/2026-11-03-management-redesign-mockup.html)
(constructed data only). Where this document and the mockup disagree, this
document wins. Its dark switcher bar is a mockup tool, not part of the design.

## Intent

Users open the page to get, or re-get, a subscription link. A new user must be
able to tell what is required, sign in, choose the subscription contents, copy
the link and reach client instructions without confusing the management and
MonoCloud passwords. A returning user must see the link on the first screen.

## Principles (each was an explicit user decision)

1. **One guided flow, one current step:** ① MonoCloud account → ② subscription
   contents → ③ subscription link → ④ import into a client. Contents are chosen
   before the link so users do not import and then reconfigure.
2. **The link is the focal point.** For a verified returning user, the link and
   its copy button sit on the first screen at both desktop and 390×844. ① then
   collapses to one line and ② is a one-line two-way choice.
3. **Format/client neutral.** Subscriptions are multi-format: mihomo works now;
   Surge (#7) and sing-box (#6) are planned. The title, next-step line, ①, ② and
   the step titles of ③/④ never name a client or kernel. Format/client names
   appear only on a format's own link row and in a client's own guide section.
   Unimplemented formats get one sentence ("尚未支持"); they get no link rows,
   buttons, tabs or switches.
4. **Device neutral.** Links are used on phones, desktops and other devices.
   The copy says "设备/其他设备/浏览器". Device names appear only as verification
   provenance (for example "已在 iPhone 上的 Clash Mi 1.0.31.1703 验证").
5. **No invented guide text.** Clash Mi steps reuse
   `static/guides/clash-mi.html` and match `docs/clash-verification.md`. Only
   references to page controls are adapted. Clash Mi does not show the Tailscale
   authorization page by itself; the log-level/copy-log procedure is the main
   path and not an "if it does not appear" fallback.
6. **No internal explanations and no identity chrome.** There is no intro
   paragraph about how the service works and no `admin` badge. The guide may
   still say that the management username is admin (a verified, issue-required
   fact).
7. **Never claim unobserved state:** whether a client imported the link, whether
   a device is on the Tailnet, or whether generation succeeded. A saved token is
   not shown as a verified account.

## Page structure

- **Header:** the product name "MonoCloud 订阅" (`<title>` too). Page heading
  "设置你的代理订阅". Below it a single live next-step line ("下一步：…"), derived
  from state.
- **① MonoCloud 账户** (current while checking, signed out, expired, unavailable,
  verified without plans, or switching):
  - Verified: one line with the "已验证" pill, "N 个可用套餐：A、B", and a
    "切换账户" link.
  - Sign-in form: email, password with show/hide, and submit with a busy state.
    A hint distinguishes the MonoCloud password from the management password and
    says the password is not saved while the login credential is stored privately
    so the user does not need to sign in again.
  - Switching: title "切换 MonoCloud 账户", "取消，保留当前账户", next-step line
    "登录另一个 MonoCloud 账户".
  - Missing OAuth plus a sign-in need: no form. One message asks the user to
    contact the deployer and reload afterwards.
  - Unavailable: "重新验证" (re-runs `api/status?verify=true`) and "重新登录".
  - Verified with zero plans: a warning plus "重新验证".
- **② 订阅内容:** a segmented two-way radio, "仅代理 | 代理 + Tailscale".
  - Selecting Tailscale shows "客户端第一次访问 Tailnet 时，需要完成一次
    Tailscale 授权。具体步骤见各客户端的接入说明。"
  - A changed selection shows an "未保存" pill, "保存" / "撤销" and "订阅链接不变".
  - The first time (saved value `null`), ② is current and has a "确认" button
    that saves the displayed choice.
  - After a later save, a persistent note tells users who already imported to
    update the subscription in the client and reconnect.
  - Read failure: an error and a retry. Save failure keeps the draft and offers
    "重试保存".
- **③ 订阅链接** (title neutral; description "不同客户端使用不同格式的链接"):
  - One row per implemented format. Today that is "mihomo · Clash Mi 等 mihomo
    内核客户端".
  - The row has an ellipsized URL, "显示完整链接", "复制链接" and "下载配置文件".
  - A privacy note follows, then "Surge、sing-box 格式尚未支持。".
  - Warnings for a loopback URL, a copy failure (expand and select the URL for
    manual copy), an unavailable account, and unsaved ② changes (the link serves
    the saved contents).
  - Copy, download and manual-copy fallback each advance the current step to ④.
- **④ 导入客户端** (description "选择你使用的客户端，展开查看步骤"):
  - One `<details>` row per client. Today that is Clash Mi only.
  - The summary shows the name, a "mihomo 格式" pill and the key action
    "我的配置 → + → 添加配置链接".
  - The body holds the verified base steps, with the available plan names added
    in the plan/node step.
  - Inside it, "可选：增加 Tailscale 能力" is a nested `<details>`, open by default
    when Tailscale is saved.
  - The verification note comes last. A closing line says Surge and sing-box
    guides arrive with their formats.
  - The row opens automatically when ④ becomes current, unless the user toggled
    it.

## Backend changes

- `/api/status?verify=true` adds `plan_names` (list of strings, same order as
  discovery). This reuses the existing `fetch_plans` call, so there are no
  per-node requests. This reverses the earlier "no plan names" privacy choice
  because #11 asks for names. The page is behind management auth and the token is
  still never returned.
- `/api/subscription` adds `tailscale_choice_saved` (bool: the saved value is
  not `null`). The effective `tailscale_enabled` keeps its current meaning.
- No other API, auth, storage or generation changes.

## Frontend implementation constraints

- Keep the native HTML/CSS/JS bundle (no framework).
- The CSP forbids inline styles and scripts, so use classes only.
- Assets, API calls and links stay relative so root and strip-prefix
  reverse-proxy mounts keep working.
- The Clash Mi guide remains a separate bundled resource embedded through
  `<!-- CLIENT_GUIDES -->`.
- Light theme with the new neutral/blue palette from the mockup.
- Accessibility:
  - The step list carries `aria-current="step"` and visually hidden step labels.
  - Form labels are associated with their inputs, and the segmented choice is a
    `fieldset` of radios.
  - Live regions are used for the next-step line and feedback.
  - There is a visible focus style.
- No horizontal overflow at 320–1280px. The long URL ellipsizes or wraps when
  expanded.

## Copy corrections outside the page

Replace phone-only assumptions in `static/guides/clash-mi.html` (title,
"确认网络", "Safari"), the `login.js` loopback message, `docs/deployment.md`
(lines about phone reachability) and `README.md` (the guide path name and
"phone/LAN"). Management-password setup stays documented in README and the
deployment docs, because the Basic-auth prompt precedes the page.

## Out of scope

Surge/sing-box formats, refresh/last-good status (#5), node counts,
showing Tailscale routes, auth-key UI, framework migration, new auth.

## Verification

- Unit tests: `plan_names` and `tailscale_choice_saved` in the API. The page
  embeds the guide without the old phone/Safari wording, and without Surge or
  sing-box guide IDs or links. Existing security/prefix tests still pass.
- Browser QA with constructed data at desktop and 390px:
  - States: signed out, verified (first-time and returning), expired with and
    without OAuth, unavailable, and a subscription read failure.
  - Actions: copy and copy fallback, saving and failing to save ②, switching
    account, and keyboard operation.
  - The link stays on the first screen, with no overflow.
  - Under a `/mono/` prefix mount, assets and API calls resolve.
