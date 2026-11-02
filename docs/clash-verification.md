# Clash/mihomo verification

## Reproducible checks (2026-11-02)

- Official asset: `https://static.monocloud.co/mono_go/Clash_ss`.
- Manifest: `https://static.monocloud.co/mono_go/update.json`.
- Exact-byte size: 243529; SHA-256:
  `9e4edb4a7907e4ae6bd8b87f56e8c4fd283243a6c9f4c782377e821ba4a6351c`.
- Official rule count: 7486. The renderer preserves their relative order and
  contents, including the final `GEOIP,CN,DIRECT` and `MATCH,Proxy` rules.
- Test core: official `MetaCubeX/mihomo` release **v1.19.32**, darwin arm64,
  Go 1.26.8, build timestamp 2026-09-30; binary reports `with_gvisor`.
- GEOIP dependency: official `MetaCubeX/meta-rules-dat` release `latest`,
  `geoip.metadb`, supplied as the core's `Country.mmdb`. Without this data the
  check attempted a download and failed in the sandbox; no rule was removed.
- Both sanitized variants passed with a constructed AES-128-GCM node at
  `192.0.2.1`, port 443, and a fake password. The enabled variant had no auth key.

Use the release's binary appropriate for your platform, then run:

```sh
mihomo -v
mihomo -t -d <private-core-data-directory> -f <private-proxy-only.yaml>
mihomo -t -d <private-core-data-directory> -f <private-tailscale.yaml>
```

These are parser/configuration checks, not network or authorization checks. The
core binary, GEOIP data, official template copy and generated files are test
artifacts in ignored local storage; they are not bundled with the application.
Normal deployments fetch official assets using the configured MonoCloud
User-Agent. This development machine received HTTP 403 both via its proxy and
directly; the official bytes above were fetched through an authorized read-only
workstation request and reverified locally. No automatic fallback or remote
workstation dependency is built into the generator.

Real-node private outputs were also generated from read-only discovery with the
saved browser-login token and the verified official bytes above. Both passed the
same core check; no node identities or credentials are included in this record.

Review regressions cover redirect rejection on both downloads, unsupported
top-level options/modes, malformed DNS mutation fields, and preservation of
existing IP-based bootstrap DNS. The template still passes those constraints.

## Clash Mi acceptance still required

| Scenario | Required result | Status |
| --- | --- | --- |
| MonoCloud only | Import, proxy access, manual node selection and ordinary DNS | Not verified on device |
| MonoCloud + Tailscale | Same proxy/selection/DNS behavior | Not verified on device |
| Tailnet access | Tailnet FQDN, IPv4 and IPv6 access; explicit advertised subnet if configured | Not verified on device |
| Authorization | Login URL exposed by the client or private auth-key provisioning | Not verified on device |
| Persistence | Same Tailnet identity and connectivity after restart using the same client state directory | Not verified on device |

Record the actual Clash Mi app/core versions with those results. A core `-t`
check, community report or sing-box test cannot substitute for this matrix.
Tailscale initializes lazily on first use; allow time for initial authorization.
Full `*.ts.net` names are configured; bare short names are not. Ensure the app
permits state writes and retains that directory when updating/importing profiles.
No claim is made yet about sleep recovery or network transitions.

## #4 service integration (implementation checks)

The actual service now provides credential-protected URLs. Both modes were
retrieved over its real HTTP endpoint using saved account discovery and an
explicit verified official snapshot, then passed mihomo v1.19.32 checks. Requests
without management Basic auth can download using the secret subscription path;
wrong-key requests return 404. Original toggle state was restored after testing.
No account/node credentials are included in this record.

Constructed-data browser tests verified copy, download, toggle save/reload and a
390px layout with no horizontal overflow. The management password and subscription
key live only in ignored private files. Device tests above remain pending; the
user's stated Clash Mi version is 1.0.31.1703. Those tests now belong to #4.

The initial LAN connection reset was traced to a macOS firewall rule blocking
incoming connections to the exact Python executable (checking its app bundle
alone did not reveal that rule). After the user allowed incoming connections,
LAN requests from both this host and a LAN peer return the expected management
401. Authenticated LAN management and native URL-credential downloads also work;
the generated configuration was checked without printing credentials. No remote
configuration was modified. Phone import and traffic behavior remain pending.
