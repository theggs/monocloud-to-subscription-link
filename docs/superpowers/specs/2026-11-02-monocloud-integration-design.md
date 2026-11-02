# MonoCloud integration

## Scope

Implement the confirmed password-grant login and Shadowsocks node endpoints from
the private research, a small shared node model, and local token storage. Python
and uv remain the stack; Tailscale stays optional and is unrelated to account access.

## Approach

Use httpx for explicit timeouts, non-followed redirects, and deterministic request
tests. Compared with urllib, it avoids custom transport/error-handling machinery.
Keep token storage in a local JSON file; an external secrets service is unnecessary.

- `POST /oauth/token`: form fields grant_type=password, username, password,
  client_id, client_secret; expect a nonempty access_token.
- `GET /api/service`: a top-level array of service records. Use outer `id` for
  node requests, not product `plan_id` or nested `plan.id`; select Shadowsocks plans.
- `GET /api/shadowsocks/{service_id}`: Bearer authorization, JSON accept header,
  configurable User-Agent and optional X-Client-Version.
- Preserve hostname, port, encryption, password, alias, and plan association in
  the shared node model. Skip explicitly disabled nodes; validate required fields.
- Use `Plan.service_id` and `Node.service_id` so product plan IDs cannot be
  confused with service-record IDs by future configuration generators.
- Account interaction is browser-only. Keep only service startup and read-only
  configuration checking in the command-line entry point. Do not expose login,
  token import, plan listing, or node retrieval as CLI commands. Shared API methods
  still support service discovery and optional explicit service IDs internally.
- Use config-relative token paths, defaulting to data_dir/token.json. Save with
  owner-only permissions through a temporary file and atomic replace. Do not save
  login passwords or raw API responses. Browser responses never include credentials.
- Treat invalid authentication as a request to log in again; do not retry login
  or assume that a refresh-token flow exists. Sanitize network/API errors.

## Evidence and limits

Authorized read-only client inspection and GET requests confirmed the service
directory and node response arrays and field types. The observed request identity
is User-Agent MonocloudGO-1.0.1 with X-Client-Version 1.0.1; both are configurable.
OAuth client constants were located in the binary but are not bundled in source,
examples, or issues. Tests use constructed values matching observed structures.
The real HTTP transport workflow is verified against a local fixture server using
constructed credentials. The user subsequently completed real browser login; the
project reused the saved token for successful service/node discovery against the
real MonoCloud API. Only sanitized outcomes are recorded.

The user subsequently authorized reading the existing client and reusing its
session for read-only GET investigation. No remote files, configuration, services,
or account state were intentionally modified. Investigation did not transfer
workstation tokens or raw node responses locally. The project's own browser login
now stores its returned token privately as designed. Fresh login and project API
retrieval are verified; keep issue #2 open until the reviewed change is merged.
