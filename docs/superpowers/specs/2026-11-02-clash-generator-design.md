# Clash/mihomo generator design

Issue: #3. Python + uv remain the implementation platform. This work adds a
callable generator, not account CLI interactions or the subscription hosting UI
reserved for #4. Tailscale is disabled by default.

## Approach

Fetch the official MonoCloud update manifest and its `Clash_ss` resource, verify
size and SHA-256 on the original bytes, then parse a normalized copy with
PyYAML's safe loader. Replace only known template placeholders before parsing;
account values are inserted into the resulting structure, never interpolated
into YAML. Preserve the official public rule list in its original order.
Maintaining a separate routing list would diverge from the requested policy;
blind string replacement would mishandle names and passwords containing YAML
syntax. A structured transformation is the chosen implementation approach.

Replace the sample proxy with all enabled API nodes and a manual `Proxy` select
group. Give collisions deterministic unique names, including names that collide
with built-in policies. Do not add automatic switching. Retain official DNS,
with explicit direct bootstrap DNS independent of the proxy/Tailscale chain.
Existing IP-based default-nameserver entries (plain or encrypted) are preserved;
only an absent setting gets the two IP defaults. Non-IP bootstrap entries fail
validation instead of silently replacing vendor policy. Manifest and resource
requests do not follow redirects. The supported top-level template fields are
mixed-port, allow-lan, mode, log-level, dns, proxies, proxy-groups and rules; unknown
fields or non-rule mode fail explicitly. DNS policy/filter shapes are checked
before mutation.

Local configuration selects the mixed port; LAN exposure defaults to disabled.

## Optional Tailscale

Add a `Tailscale` outbound only when enabled. Its underlying dialer remains direct; SS node resolution uses independent
bootstrap resolvers. The original proxy-backed dialer was removed after device
logs and a two-variant mihomo v1.19.32 reproduction confirmed upstream #3142:
proxy-backed UDP wildcard binding fails before login, while direct binding
succeeds and emits an authorization hint. The client network must allow Tailscale
control/DERP/STUN and peer connections directly.
Route Tailnet IPv4/IPv6 and `ts.net` before the official LAN rules. Query Tailnet
FQDNs through `ts://Tailscale` and exclude them from fake-IP. Optional explicit
subnet CIDRs are routed to Tailscale with `accept-routes`; no exit node is used.
Keep all original public rules in their relative order after these additions.

Private TOML contains optional hostname, auth key, control URL, client-side state
directory and subnet routes. State paths refer to the client, not this server's
data directory. Use a stable non-ephemeral node and persistent client state.
Without an auth key, authorization uses the login URL emitted by the core. The
client must expose that URL; otherwise provision a private auth key. Never
commit generated configs, keys, or personal Tailnet values. Auth keys in generated
configs are sensitive, just like SS passwords.

## Interfaces and verification

`fetch_template(http, settings) -> dict` downloads and checks the official asset.
`generate_clash(template, nodes, clash, tailscale) -> str` returns complete YAML
without modifying inputs. `generate_subscription(config, http) -> str` composes
saved-token loading, node discovery, template fetch and rendering for #4.
Generation performs no file writes and never logs credentials or response bodies.
Errors reject the attempted generation rather than emitting partial output.
Refresh scheduling and retaining the last published config belong to #5.

Tests cover digest/size failures, malformed templates, node name collisions,
YAML-sensitive credentials, all-node inclusion, input immutability, rule order,
proxy-only omission, Tailscale DNS/routing and orchestration failures. Check both
sanitized variants with official mihomo v1.19.32. Record actual results separately
from still-required Clash Mi iOS tests: proxy access, selection, DNS, Tailnet
FQDN/IP access and persistent identity after restart. Core parsing alone cannot
close the phone acceptance criteria.

Sources: https://static.monocloud.co/mono_go/update.json,
https://wiki.metacubex.one/config/proxies/tailscale/,
https://wiki.metacubex.one/config/dns/type/,
https://wiki.metacubex.one/config/dns/.
