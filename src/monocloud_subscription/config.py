"""Load the small set of configuration options implemented so far."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from monocloud_subscription.monocloud import MonoCloudSettings


@dataclass(frozen=True)
class Config:
    data_dir: Path
    token_file: Path
    monocloud: MonoCloudSettings = field(default_factory=MonoCloudSettings)


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
    return Config(data_dir=data_dir, token_file=token_path, monocloud=api)
