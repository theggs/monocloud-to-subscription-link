# Clash/mihomo verification

## Device acceptance completed (2026-11-02–03)

The user tested **Clash Mi 1.0.31.1703 on iPhone** within the controlled home LAN.
The app's actual bundled core version was not independently read from its About
screen; the separately tested desktop core is identified below.

| Scenario | Result and evidence |
| --- | --- |
| MonoCloud only | User confirmed protected URL import, google.com and baidu.com access, manual node switching, and subscription refresh with continued access. No Tailscale authorization was required. |
| MonoCloud + Tailscale | User confirmed both public sites remain accessible while Tailnet access is enabled. |
| Tailnet access and DNS | User confirmed the existing HTTP service is reachable by Tailnet IPv4 and full Tailnet FQDN. The management authentication dialog/page is the expected response. |
| Authorization | Completed in the browser using the URL obtained from Core Logs → More → Copy. No automatic authorization prompt appeared in this test. |
| State persistence | User disconnected, exited/reopened the app, reconnected, then updated the same subscription and reconnected again. Access remained normal without new authorization. Read-only Tailnet status confirmed the original device ID, unchanged peer count and an online peer. |

Original logs, authorization URLs, device IDs, actual private endpoints and
credentials are not included here. These results satisfy the device workflow
acceptance moved from #3 into #4. They do not establish IPv6 reachability, advertised
subnet routing, sleep recovery, network transitions or updates outside the home
network; those were not tested. The subscription server distributes configuration,
while the generated SS outbounds target MonoCloud nodes directly and Tailscale
runs inside the client. It is not a phone traffic relay.

## Core and service verification

- Official asset: `https://static.monocloud.co/mono_go/Clash_ss`.
- Manifest: `https://static.monocloud.co/mono_go/update.json`.
- Exact-byte size: 243529; SHA-256:
  `9e4edb4a7907e4ae6bd8b87f56e8c4fd283243a6c9f4c782377e821ba4a6351c`.
- Official rule count: 7486, preserved in order and content, including the final
  `GEOIP,CN,DIRECT` and `MATCH,Proxy` rules.
- Desktop core: official `MetaCubeX/mihomo` **v1.19.32**, darwin arm64, Go 1.26.8,
  build timestamp 2026-09-30, tags `with_gvisor`.
- GEOIP: official `MetaCubeX/meta-rules-dat` release `latest`, `geoip.metadb`,
  supplied as `Country.mmdb`. No GEOIP rule was removed to make validation pass.
- Both sanitized modes passed with a constructed AES-128-GCM node at `192.0.2.1`,
  port 443, and fake credentials. Both private real-node outputs also passed.
- Real protected HTTP downloads in both modes were validated with saved-account
  discovery and the verified official snapshot, followed by core checks.
- Constructed-data browser checks verified copy, YAML download, toggle save/reload
  and a 390px layout with no horizontal overflow.

Run the release binary appropriate for the test platform:

```sh
mihomo -v
mihomo -t -d <private-core-data-directory> -f <private-proxy-only.yaml>
mihomo -t -d <private-core-data-directory> -f <private-tailscale.yaml>
```

The binary, GEOIP data, template copies, runtime state and generated files remain
in ignored local storage. The application does not bundle private data or these
test artifacts. Core parsing and constructed browser tests are distinct from the
user-confirmed phone results above.

The development machine receives a Cloudflare challenge from the official asset
host. Test bytes were obtained through an authorized read-only workstation request
and reverified locally. The explicit `template_dir` configuration supports that
operator-provided official snapshot, with size/SHA-256 checks intact. There is no
implicit fallback, workstation dependency or claim of automatic snapshot freshness.
Normal HTTPS downloads still require access to the official asset host.

## Startup issues found and resolved

**Proxy-backed UDP binding.** Device logs showed Tailnet rules matching followed
by `tsnet: wgengine: magicsock: Rebind IPv4 failed: failed to bind any ports (tried
[0])`, before login. A local two-variant reproduction with the official desktop
core and a constructed SS node reproduced the UDP and empty-target resolution
errors only with `dialer-proxy: Proxy`. Removing that field eliminated the errors
and produced a login hint. The generator now leaves Tailscale's underlying dialer
direct; the phone subsequently completed authorization and Tailnet access. The
client network must permit Tailscale control/DERP/STUN and peer connections.
See [upstream #3142](https://github.com/MetaCubeX/mihomo/issues/3142).

**Authorization visibility.** mihomo sends tsnet user messages to its info logger.
For enabled, unkeyed Tailscale, the renderer raises hidden warning/error/silent
logging to info. Clash Mi also has its own core log-level override, default error;
select info there for first-time login. Core Logs displays plain text, but its
More menu supports full-text copy and file sharing. Copy into a private note,
find `login.tailscale.com`, and open only that URL. Keep the VPN connected until
browser authorization completes and Tailnet access works; then test restart.
No auth-key UI or automatic browser-launch feature was added. See the tagged
[log viewer source](https://github.com/KaringX/clashmi/blob/v1.0.31.1703/lib/screens/richtext_viewer.screen.dart).

**LAN firewall.** The initial reset was traced to macOS Firewall blocking the exact
Python executable. Checking its app bundle alone missed that rule. After the user
allowed incoming connections, local and LAN-peer HTTP probes returned the expected
management 401. The phone also needed to join Wi-Fi. No remote configuration was
changed; only the user-authorized local Python incoming rule was allowed.
