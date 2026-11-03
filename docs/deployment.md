# Deployment and private configuration

This document is for the person running the service. Account operations, plan/node
selection and client import/update instructions belong to the management page's
**客户端接入指南**. The README Quick start covers only the first local startup.

## Docker Compose

Requires Docker with the Compose plugin; host Python and uv are not needed.
From the repository root:

```sh
mkdir -p .local
chmod 700 .local
cp deploy/config.example.toml .local/container.toml
```

Edit `.local/container.toml` to supply the private MonoCloud `client_id` and
`client_secret`. Create `.local/service.env` containing your chosen management
password (the same variable as direct execution):

```dotenv
MONOCLOUD_WEB_PASSWORD=replace-with-your-own-private-password
```

Keep the parent `.local` directory private. The mounted TOML must be readable by
container UID 10001; the following uses file readability inside a private parent
directory. The environment file is read by Compose, not the container user.

```sh
chmod 644 .local/container.toml
chmod 600 .local/service.env
docker compose up -d --build
```

Open `http://127.0.0.1:8080/`, authenticate as `admin` using the password you chose,
then follow the page's steps: account, subscription contents, link and client import. The image installs locked
production dependencies during build; startup does not install packages.

By default Compose publishes only on host loopback. For access from other devices on a
trusted LAN, set `server.public_url` in `.local/container.toml` to the reachable host URL
(for example `http://192.168.1.10:8080`), then run:

```sh
BIND_ADDRESS=0.0.0.0 docker compose up -d
```

Keep those environment overrides on subsequent Compose commands; `PORT` can also
change the published host port. The internal listen address remains `0.0.0.0:8080`.
Use the actual published port in `public_url`. For HTTPS deployment, publish to
the reverse proxy as appropriate and follow the transport section below.

```sh
docker compose logs --tail=50 subscription
docker compose restart subscription   # after editing mounted TOML
docker compose up -d --force-recreate # after editing service.env
docker compose down                 # retains the named data volume
```

The `subscription-data` named volume mounts the complete `/data` directory and
preserves login tokens, subscription URL credentials and saved settings across
container recreation. Do not use `down -v` unless deliberately discarding this
state. Keep the same Compose project name when upgrading. Back up this volume
privately. Do not mount individual JSON files: updates replace files atomically.
For a host bind directory instead, grant UID/GID `10001:10001` write access first.
Any custom `token_file` must also point into persisted writable storage.
A fresh volume starts without an account login and creates a new subscription
URL credential; it does not automatically import a direct installation's data.
To migrate existing state, stop the old service, copy its complete data directory
into the volume and set ownership to `10001:10001` before starting the container.
Stop any existing listener on the same host port before switching deployments.

The image runs as UID/GID `10001:10001`, with one Uvicorn process receiving stop
signals directly. Uvicorn allows active requests up to 25 seconds to finish before
cancelling them; Compose waits 35 seconds before force-killing the container.
This is a bounded shutdown, not a guarantee that every long subscription generation
finishes. It needs no privileged mode, TUN device, or server-side
Tailscale daemon. Client `tailscale.state_dir` remains a client-side path.
For an explicit official template snapshot, add a read-only directory mount at
`/templates`, make its files readable by UID 10001, and enable the example's
`template_dir` setting. No snapshot or private configuration is baked into the
image. `.dockerignore` allowlists build inputs; Git ignore rules alone are
insufficient for this ([Docker documentation](https://docs.docker.com/build/concepts/context/#dockerignore-files)).

Without Compose, build with `docker build -t monocloud-subscription:local .` and
run the same image with your environment file, read-only config mount, persistent
`/data` volume and port publishing. The default command uses
`/config/config.toml`; arguments can override it. Building follows the
[uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
using a separate build stage; uv and build sources are absent from the runtime.

For a repeatable smoke check with disposable configuration and fake credentials:

```sh
docker build -t monocloud-subscription:local .
uv run --locked python scripts/check_container.py
```

The check creates its own randomly named Compose project and deletes only its
test volume afterward; it never uses your `.local` credentials or running service.
It replaces the upstream login with a 12-second fake response to verify that
an active request can complete during a normal Compose stop, then recreates the
container to check persisted state.

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

With no management password configured, use direct loopback access only. Binding
beyond loopback requires the password. **Always set `MONOCLOUD_WEB_PASSWORD` when
using a reverse proxy or tunnel, even if the application listens on loopback.**
A local proxy can make external requests appear local; the Host-header check
does not protect an unauthenticated backend behind such a proxy.
Native client subscription downloads use
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
without it, links use the management browser's origin. Other devices cannot
reach a loopback URL belonging to the server. A reverse-proxy URL may include a mount
prefix, for example `https://example.com/mono`. Configure the proxy to redirect
`/mono` to `/mono/`, strip `/mono` when forwarding requests, and route the entire
`/mono/` subtree to this service. Page assets and API calls resolve relative to
that trailing-slash page URL. Subscription URLs use the configured `public_url`.

Every device that uses the subscription must be able to reach the address and
port when importing/updating. For LAN deployment, confirm LAN/Wi-Fi connectivity and firewall permission for the exact
runtime executable. If loopback works but LAN connections reset, check that
executable's incoming-connection rule; checking only its application bundle can
miss a blocked executable. Do not disable the whole firewall for this service.

## Transport and reverse proxy

Controlled home-LAN HTTP is a transport assumption, not encryption. It exposes
management/account credentials, bearer subscription URLs and returned node
credentials to observers on that network. Use HTTPS for access across untrusted
networks. TLS termination remains a deployment choice.

When using an HTTPS reverse proxy:

- Set `MONOCLOUD_WEB_PASSWORD` on the backend regardless of its bind address.
- Forward the original `Host` and set `X-Forwarded-Proto`.
- Uvicorn trusts forwarded headers from loopback by default. For a proxy elsewhere,
  set `FORWARDED_ALLOW_IPS` to its specific trusted address; do not trust arbitrary
  client-supplied forwarded headers.
- Preserve matching scheme/hostname/effective port for the management Origin check.
- Do not cache responses or record secret subscription paths/configuration bodies
  in the proxy's access/debug logs. Application access logs are disabled, and
  management/download responses use `no-store`.

The service distributes configuration; each client device connects to MonoCloud and
Tailnet itself. Subscription updates outside the home network require a reachable server
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
