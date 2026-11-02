# Login page for issue #2

## Scope and approach

Add a single browser page for MonoCloud email/password login, using the existing
OAuth client and private token store. Display pending, success, failure, and saved
token status. Do not include Tailscale settings, subscription links, node browsing,
or update controls; those belong to their respective issues.

Serve bundled HTML/CSS/JavaScript from a small FastAPI application, started by
`monocloud-subscription --config PATH serve`. This keeps the Python + uv project
and deployment-independent entry point. A separate SPA/build pipeline would add
unnecessary setup for one form; a CLI-only flow does not meet the requested UI.
Per the user's final direction, browser login is the sole account interaction;
the CLI retains only `serve` and `check`.

## Behavior

- Read OAuth application parameters only from existing private configuration.
  Never expose their values to the browser.
- Submit email and password as same-origin JSON. Save only the returned token
  after successful upstream login. Preserve an existing token on failure.
- Do not store email/password in localStorage, sessionStorage, server files, or
  logs. Clear the password field after each attempt. Browser-managed password
  autofill remains available to the user.
- Return concise errors without upstream response bodies, request contents, or
  framework validation payloads that could echo passwords.
- Report a saved token as saved, not proof that it is currently valid upstream.
- Serve locally by default on 127.0.0.1:8080. Non-loopback binding requires
  MONOCLOUD_WEB_PASSWORD and a single HTTP Basic management password. No accounts,
  roles, sessions, database, or permission framework. Use HTTPS for deployment
  beyond local/private access; TLS termination remains a deployment choice.
- Reject cross-origin state-changing requests and do not allow credential-bearing
  cross-origin access. Disable request access logs and browser caching.

## Visual design

A restrained, warm ivory canvas with ink typography and a single moss-green
accent. One clear login form, compact status indicator, responsive layout, visible
keyboard focus, labeled controls, accessible error announcements, and reduced
motion support. No external fonts, scripts, analytics, or assets.

## Verification

Use constructed accounts to test HTTP login/token persistence, safe failures and
validation, missing OAuth settings, status privacy, Basic access, cross-origin
rejection, and static asset packaging. Verify form behavior in a real browser.
Do not perform a real MonoCloud login during automated tests.
