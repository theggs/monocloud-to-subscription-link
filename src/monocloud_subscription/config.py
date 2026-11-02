"""Load the small set of configuration options implemented so far."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path


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
    return Config(data_dir=data_dir)
