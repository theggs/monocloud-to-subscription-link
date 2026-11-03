"""Load the small set of configuration options implemented so far."""

import tomllib
from dataclasses import dataclass, field
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urlsplit

from monocloud_subscription.clash import ClashSettings, TailscaleSettings
from monocloud_subscription.monocloud import MonoCloudSettings
from monocloud_subscription.subscription_state import valid_subscription_key


@dataclass(frozen=True)
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8080
    public_url: str = ""


@dataclass(frozen=True)
class Config:
    data_dir: Path
    token_file: Path
    monocloud: MonoCloudSettings = field(default_factory=MonoCloudSettings)
    clash: ClashSettings = field(default_factory=ClashSettings)
    tailscale: TailscaleSettings = field(default_factory=TailscaleSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    subscription_key: str = field(default="", repr=False)
    template_dir: Path | None = None


def load_config(path: Path) -> Config:
    """Read configuration without creating directories or changing state."""
    try:
        with path.open("rb") as file:
            values = tomllib.load(file)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid TOML configuration.") from None
    except OSError:
        raise ValueError("Cannot read configuration file.") from None

    value = values.get("data_dir")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("data_dir must be a nonempty string.")

    data_dir = Path(value)
    if not data_dir.is_absolute():
        data_dir = path.resolve().parent / data_dir
    token_file = values.get("token_file")
    if token_file is None:
        token_path = data_dir / "token.json"
    else:
        if not isinstance(token_file, str) or not token_file.strip():
            raise ValueError("token_file must be a nonempty string.")
        token_path = Path(token_file)
        if not token_path.is_absolute():
            token_path = path.resolve().parent / token_path

    settings = values.get("monocloud", {})
    if not isinstance(settings, dict):
        raise ValueError("monocloud must be a TOML table.")
    options = {}
    for key in (
        "base_url",
        "user_agent",
        "client_version",
        "client_id",
        "client_secret",
    ):
        if key in settings:
            if not isinstance(settings[key], str):
                raise ValueError(f"monocloud.{key} must be a string.")
            options[key] = settings[key]
    api = MonoCloudSettings(**options)
    try:
        url = urlsplit(api.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise ValueError
        _ = url.port
    except ValueError:
        raise ValueError(
            "monocloud.base_url must be an HTTPS API URL without credentials."
        ) from None
    for value in (api.user_agent, api.client_version):
        if not value.isascii() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError(
                "MonoCloud request headers must contain printable ASCII only."
            )
    clash_values = values.get("clash", {})
    if not isinstance(clash_values, dict):
        raise ValueError("clash must be a TOML table.")
    clash_port = clash_values.get("mixed_port", 7890)
    if type(clash_port) is not int or not 1 <= clash_port <= 65535:
        raise ValueError("clash.mixed_port must be an integer between 1 and 65535.")
    ts_values = values.get("tailscale", {})
    if not isinstance(ts_values, dict):
        raise ValueError("tailscale must be a TOML table.")
    ts_options = {}
    for key in ("enabled", "hostname", "state_dir", "auth_key", "control_url"):
        if key not in ts_values:
            continue
        value = ts_values[key]
        if (key == "enabled" and type(value) is not bool) or (
            key != "enabled" and not isinstance(value, str)
        ):
            raise ValueError(f"Invalid tailscale.{key} type.")
        ts_options[key] = value
    if not ts_options.get("state_dir", "tailscale").strip():
        raise ValueError("tailscale.state_dir must be a nonempty client-side path.")
    if ts_options.get("control_url"):
        try:
            control = urlsplit(ts_options["control_url"])
            if (
                control.scheme != "https"
                or not control.hostname
                or control.username
                or control.password
            ):
                raise ValueError
            _ = control.port
        except ValueError:
            raise ValueError(
                "tailscale.control_url must be an HTTPS URL without credentials."
            ) from None
    routes = ts_values.get("routes", [])
    try:
        if not isinstance(routes, list) or any(
            not isinstance(route, str) for route in routes
        ):
            raise ValueError
        networks = [ip_network(route, strict=True) for route in routes]
        if any(network.prefixlen == 0 for network in networks):
            raise ValueError
    except ValueError:
        raise ValueError(
            "tailscale.routes must be explicit subnet CIDRs, not default routes."
        ) from None
    ts_options["routes"] = tuple(str(network) for network in networks)
    server = values.get("server", {})
    if not isinstance(server, dict):
        raise ValueError("server must be a TOML table.")
    host = server.get("host", "127.0.0.1")
    port = server.get("port", 8080)
    public_url = server.get("public_url", "")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("server.host must be a nonempty listen address.")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("server.port must be between 1 and 65535.")
    try:
        if not isinstance(public_url, str):
            raise ValueError
        if public_url:
            url = urlsplit(public_url)
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.hostname in ("0.0.0.0", "::")
            ):
                raise ValueError
            _ = url.port
    except ValueError:
        raise ValueError(
            "server.public_url must be a reachable HTTP(S) base URL without credentials or query."
        ) from None
    subscription = values.get("subscription", {})
    if not isinstance(subscription, dict):
        raise ValueError("subscription must be a TOML table.")
    key = subscription.get("key", "")
    if key != "" and not valid_subscription_key(key):
        raise ValueError("subscription.key must contain 32-128 URL-safe characters.")
    template_dir = values.get("template_dir")
    if template_dir is not None:
        if not isinstance(template_dir, str) or not template_dir.strip():
            raise ValueError("template_dir must be a nonempty directory path.")
        template_dir = Path(template_dir)
        if not template_dir.is_absolute():
            template_dir = path.resolve().parent / template_dir
    return Config(
        data_dir=data_dir,
        token_file=token_path,
        monocloud=api,
        clash=ClashSettings(clash_port),
        tailscale=TailscaleSettings(**ts_options),
        server=ServerSettings(host.strip(), port, public_url.rstrip("/")),
        subscription_key=key,
        template_dir=template_dir,
    )
