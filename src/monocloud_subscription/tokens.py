"""Simple private local token storage."""

import json
import math
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class Session:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: float | None = None


def validate_session(session: Session) -> None:
    try:
        valid_expiry = session.expires_at is None or (
            type(session.expires_at) in (int, float)
            and math.isfinite(session.expires_at)
            and session.expires_at > 0
        )
    except OverflowError:
        valid_expiry = False
    if (
        not valid_token(session.access_token)
        or (
            session.refresh_token is not None and not valid_token(session.refresh_token)
        )
        or not valid_expiry
    ):
        raise ValueError("Invalid saved account session.")


def valid_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.isascii()
        and not any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    )


class TokenStore:
    def __init__(self, path: Path):
        self.path = path
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(str(path.resolve()), threading.RLock())

    @contextmanager
    def locked(self):
        """Serialize account operations across threads in the single-worker service."""
        with self._lock:
            yield

    def load(self) -> str:
        return self.load_session().access_token

    def load_session(self) -> Session:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(
                "No saved token. Sign in through the web interface."
            ) from None
        except (ValueError, UnicodeDecodeError):
            raise ValueError(
                "Invalid token file. Sign in through the web interface."
            ) from None
        except OSError:
            raise ValueError("Cannot read token file.") from None
        if isinstance(values, dict) and values.get("reauth_required") is True:
            raise ValueError("Sign in again through the web interface.")
        if not isinstance(values, dict) or not valid_token(values.get("access_token")):
            raise ValueError("Invalid token file. Sign in through the web interface.")
        session = Session(
            values["access_token"],
            values.get("refresh_token"),
            values.get("expires_at"),
        )
        try:
            validate_session(session)
        except ValueError:
            raise ValueError(
                "Invalid token file. Sign in through the web interface."
            ) from None
        return session

    def save(self, token: str) -> None:
        self.save_session(Session(token))

    def save_session(self, session: Session) -> None:
        with self._lock:
            self._save_session(session)

    def _save_session(self, session: Session) -> None:
        validate_session(session)
        values = {"access_token": session.access_token}
        if session.refresh_token is not None:
            values["refresh_token"] = session.refresh_token
        if session.expires_at is not None:
            values["expires_at"] = session.expires_at
        self._write_values(values)

    def invalidate(self) -> None:
        """Persist a terminal re-login state without retaining rejected credentials."""
        with self._lock:
            self._write_values({"reauth_required": True})

    def _write_values(self, values: dict) -> None:
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(values, file, allow_nan=False)
            os.replace(temporary, self.path)
        except OSError:
            raise ValueError("Cannot save token file.") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
