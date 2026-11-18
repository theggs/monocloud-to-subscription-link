# MonoCloud 1.5 integration

Adapt the existing Python service to MonoCloud 1.5.0 API v2. Keep the current
subscription URLs, browser workflow, plan groups and optional Tailscale behavior.
Use explicit `api_version = "legacy"` for the old endpoints; do not silently
downgrade on authentication, decryption or schema failures.

Use cryptography's X25519, HKDF-SHA256 and AESGCM implementations. Response key ID
and 32-byte shared key are private operator settings, like the existing OAuth
credentials. Never bundle values extracted from the proprietary application.
Accept encrypted server lists when encryption is requested; reject plaintext
downgrades, mismatched key IDs, malformed encodings and invalid authentication tags.
Map v2 service/server fields to the existing Plan/Node models. Export Shadowsocks
nodes from mixed accounts and omit other protocols. Fail explicitly for invalid
or unsupported Shadowsocks fields and subscriptions without compatible nodes.

Persist access token, optional refresh token and absolute expiry atomically in the
existing owner-only token file. Read old access-token-only files. Serialize
refresh and publication within this single-worker service; never refresh a revoked
session or retry a rejected refresh. Never expose token values in browser responses,
reprs, logs or errors. Preserve the saved subscription URL and Tailscale choice.

Native-binary inspection supplies the protocol evidence; constructed cryptographic
fixtures and HTTP transports supply automated verification. A live account check
remains separate from offline verification. Do not claim that unsupported Papaya
nodes will work with unmodified third-party clients.
