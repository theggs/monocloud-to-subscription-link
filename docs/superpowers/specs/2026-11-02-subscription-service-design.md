# Protected subscription service (#4)

## Scope and approach

Extend the existing FastAPI/native HTML service with a small subscription card,
not a dashboard. Keep browser login; add link display/copy/download and a persisted
Tailscale opt-in toggle. Reuse the official-policy generator. No account CLI,
deployment scaffolding, RBAC, auto-refresh or last-good publisher (#5).

GET /subscriptions/{key}/clash.yaml supports GET/HEAD and returns complete YAML
only with the correct URL-safe, high-entropy credential. It uses that credential
instead of management Basic auth, so Clash Mi can update without browser sessions.
All other routes retain existing management protection and same-origin JSON POST
checks. Disable request access logs; return no-store and no-referrer headers.
Wrong/unknown paths fail without fetching nodes or exposing keys. A future format
can add a sibling suffix without redesigning credentials.

Generate a 32-byte random key once, persist it with owner-only permissions in
`data_dir/subscription.json`, and retain it across restarts. An optional private
`subscription.key` override is supported. The same state file stores an optional
Tailscale enabled override; otherwise use TOML. Save atomically; malformed existing
state fails explicitly rather than resetting URLs or overwriting state. One
process owns this small file; multi-worker coordination is out of scope.

GET /api/subscription returns the protected URL and effective enabled flag to
management only. POST /api/subscription accepts only the enabled flag; disabling
Tailscale preserves all private TOML connection settings. API responses never
include node/token/key-file contents. Link URLs necessarily contain the bearer
credential. All rendering is server-generated; errors return stable sanitized
codes. No secret is placed in browser localStorage or third-party resources.

`[server]` supplies host/port and optional public_url. CLI --host/--port override
TOML; defaults remain loopback:8080. public_url is the externally reachable base
URL (including any proxy mount prefix), never a bind wildcard. Without it, use
the authenticated browser origin and explain loopback links cannot reach phones.
Remote management still requires MONOCLOUD_WEB_PASSWORD. Controlled LAN HTTP is
explicitly a deployment transport choice; recommend HTTPS beyond that environment.

## Official asset reachability

Normal generation downloads the official HTTPS manifest/resource. This environment
receives a Cloudflare challenge. An explicit optional `template_dir` therefore
reads exactly `update.json` and `Clash_ss` from an operator-supplied official
snapshot, verifies size/SHA-256 against its manifest, then uses the same validator.
There is no implicit fallback, workstation dependency or alternate routing policy.
Relative paths resolve against TOML; snapshots are not auto-updated. #5 owns
scheduled freshness/reliability. Download failures never return partial YAML.

## UI and verification

Keep warm ivory/moss styling and current login. A compact second card shows the
Clash/mihomo link, copy/download controls, Tailscale toggle and save/error states.
No node/password display or broad settings editor. Implement via native assets.

Tests cover persisted credentials/toggle, wrong-key denial before generation,
Basic-auth separation, HEAD, error privacy/no-store, same-origin settings POST,
client settings preserving secrets, local snapshot digest/size verification,
server options and CLI overrides. Test the browser using constructed credentials.
Then run actual Clash Mi 1.0.31.1703 on the user's LAN: URL import/update in both
modes, ordinary proxy/DNS and manual node selection, Tailnet FQDN/IP access,
authorization and same identity after restart. Device outcomes require the user;
core checks and fake browser runs cannot claim them. Do not merge/close #4 before
required acceptance is complete or the user explicitly revises the boundary.
