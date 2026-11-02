"""Small private state for stable subscription URLs and the Tailscale toggle."""

import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def valid_subscription_key(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value) is not None
    )


@dataclass(frozen=True)
class SubscriptionState:
    key: str = field(repr=False)
    tailscale_enabled: bool | None = None


class SubscriptionStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> SubscriptionState:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            state = SubscriptionState(secrets.token_urlsafe(32))
            self._save(state)
            return state
        except (OSError, ValueError):
            raise ValueError("Cannot read subscription state.") from None
        if not isinstance(values, dict) or not valid_subscription_key(
            values.get("key")
        ):
            raise ValueError("Invalid subscription state.")
        enabled = values.get("tailscale_enabled")
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("Invalid subscription state.")
        return SubscriptionState(values["key"], enabled)

    def set_enabled(self, enabled: bool) -> None:
        state = self.load()
        self._save(SubscriptionState(state.key, enabled))

    def _save(self, state: SubscriptionState) -> None:
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(
                    {"key": state.key, "tailscale_enabled": state.tailscale_enabled},
                    file,
                )
            os.replace(temporary, self.path)
        except OSError:
            raise ValueError("Cannot save subscription state.") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
