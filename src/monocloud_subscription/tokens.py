"""Simple private local token storage."""

import json
import os
import tempfile
from pathlib import Path


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

    def load(self) -> str:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError("No saved token. Run import-token or login.") from None
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Invalid token file. Run import-token or login.") from None
        except OSError:
            raise ValueError("Cannot read token file.") from None
        if not isinstance(values, dict) or not valid_token(values.get("access_token")):
            raise ValueError("Invalid token file. Run import-token or login.")
        return values["access_token"]

    def save(self, token: str) -> None:
        if not valid_token(token):
            raise ValueError("Invalid access token.")
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump({"access_token": token}, file)
            os.replace(temporary, self.path)
        except OSError:
            raise ValueError("Cannot save token file.") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
