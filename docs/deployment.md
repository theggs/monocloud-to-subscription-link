# Deployment and private configuration

This document is for the person running the service. Account operations, plan/node
selection and client import/update instructions belong to the management page's
**客户端接入指南**. The README Quick start covers only the first local startup.

## Management credentials

The deployer chooses `MONOCLOUD_WEB_PASSWORD`; the application does not generate a
management password. HTTP Basic authentication uses username `admin`. This protects
the management page and APIs and is separate from MonoCloud account login and the
random subscription URL credential.

Supply the value through your deployment's private process environment. For the
README's uv example, create `.local/service.env` with the chosen value, restrict
its permissions, and let `uv run --env-file .local/service.env` load it. The file is
ignored by Git. Direct execution, a container or a process manager can supply the
same environment variable using their own private environment mechanism. Do not
put real passwords in committed files or process command-line arguments.

Startup identifies the management username and variable name without printing the
password. Someone opening the management page must obtain that password from the
deployer; the MonoCloud account password will not unlock its browser prompt.

With no management password configured, access is limited to loopback. Binding
beyond loopback requires the password. Native client subscription downloads use
the secret URL path, independently of management Basic auth.

## Listen address and client URL

The default listen address is `127.0.0.1:8080`. Configure `[server]` in private TOML;
CLI `--host` and `--port` override it. For a controlled home LAN, for example:

```toml
[server]
host = "0.0.0.0"
port = 8080
public_url = "http://192.168.1.10:8080"
```

Replace the example IP with your server's reachable address. The bind wildcard
is not a browser address. `public_url` is the base URL shown in subscription links;
without it, links use the management browser's origin. A phone cannot reach a
loopback URL belonging to the server. A reverse-proxy URL may include a mount
prefix if the proxy routes it appropriately.

The phone must be able to reach the address and port when importing/updating. For
LAN deployment, confirm Wi-Fi connectivity and firewall permission for the exact
runtime executable. If loopback works but LAN connections reset, check that
executable's incoming-connection rule; checking only its application bundle can
miss a blocked executable. Do not disable the whole firewall for this service.

## Transport and reverse proxy

Controlled home-LAN HTTP is a transport assumption, not encryption. It exposes
management/account credentials, bearer subscription URLs and returned node
credentials to observers on that network. Use HTTPS for access across untrusted
networks. TLS termination remains a deployment choice.

When using an HTTPS reverse proxy:

- Forward the original `Host` and set `X-Forwarded-Proto`.
- Uvicorn trusts forwarded headers from loopback by default. For a proxy elsewhere,
  set `FORWARDED_ALLOW_IPS` to its specific trusted address; do not trust arbitrary
  client-supplied forwarded headers.
- Preserve matching scheme/hostname/effective port for the management Origin check.
- Do not cache responses or record secret subscription paths/configuration bodies
  in the proxy's access/debug logs. Application access logs are disabled, and
  management/download responses use `no-store`.

The service distributes configuration; the phone connects to MonoCloud and Tailnet
itself. Subscription updates outside the home network require a reachable server
URL; that access method is not selected by the application.

## Runtime state and official templates

Preserve the configured `data_dir` and any separately configured `token_file`.
`subscription.json` stores the stable random URL credential and saved Tailscale
switch override. Losing it changes automatically generated client URLs. Run one
application worker for this file store; path/permission semantics are described
in the README's [configuration section](../README.md#configuration-and-private-data).

Tailscale device state belongs to the client, not this server. Keep the same
client state directory across restarts and profile refreshes; follow the optional
Tailscale section in the client guide for authorization and verification.

Normal generation fetches the official manifest/template over HTTPS. If the host
presents an automated-client challenge, the explicit `template_dir` option reads
an operator-provided official snapshot containing `update.json` and `Clash_ss`.
Size and SHA-256 checks still apply. This performs no automatic download, fallback
or refresh; the operator must manage snapshot provenance/freshness. See the
[verification record](clash-verification.md). Scheduled refresh and last-good
publication remain separate work.
