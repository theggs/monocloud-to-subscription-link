"""Authenticated server-list transport for the observed MonoCloud v2 protocol."""

import base64
import binascii
import json

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def decode_base64(value: object, length: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise ValueError("Invalid server-list encoding.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid server-list encoding.") from None
    if length is not None and len(decoded) != length:
        raise ValueError("Invalid server-list key or nonce length.")
    return decoded


class ServerListCipher:
    def __init__(self, key_id: str, shared_key: str):
        if (
            not key_id
            or not key_id.isascii()
            or any(ord(c) <= 32 or ord(c) >= 127 for c in key_id)
        ):
            raise ValueError("Invalid server-list key ID.")
        self.key_id = key_id
        self._shared_key = decode_base64(shared_key, 32)
        self._private = X25519PrivateKey.generate()
        self._public = self._private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    def request_headers(self) -> dict[str, str]:
        return {
            "X-Response-Key-Id": self.key_id,
            "X-Response-Public-Key": base64.b64encode(self._public).decode("ascii"),
        }

    def decode(self, value: object) -> list:
        try:
            if (
                not isinstance(value, dict)
                or value.get("encryption") != "x25519-hkdf-sha256-aes-256-gcm"
                or value.get("key_id") != self.key_id
            ):
                raise ValueError
            public = decode_base64(value.get("public_key"), 32)
            nonce = decode_base64(value.get("nonce"), 12)
            ciphertext = decode_base64(value.get("ciphertext"))
            if len(ciphertext) < 16 or len(ciphertext) > 16 * 1024 * 1024:
                raise ValueError
            shared = self._private.exchange(X25519PublicKey.from_public_bytes(public))
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._shared_key,
                info=b"monocloud server list v1" + self._public + public,
            ).derive(shared)
            data = json.loads(AESGCM(key).decrypt(nonce, ciphertext, None))
            if not isinstance(data, list):
                raise ValueError
            return data
        except (ValueError, TypeError, InvalidTag, UnicodeDecodeError):
            raise ValueError(
                "Cannot authenticate or decode the MonoCloud server list."
            ) from None
