import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monocloud_subscription.tokens import TokenStore


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state" / "token.json"
        self.store = TokenStore(self.path)

    def test_round_trip_uses_private_file(self):
        self.store.save("synthetic-token")
        self.assertEqual(self.store.load(), "synthetic-token")
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_missing_token_directs_user_to_web_login(self):
        with self.assertRaisesRegex(ValueError, "web interface"):
            self.store.load()

    def test_invalid_storage_does_not_expose_contents(self):
        self.path.parent.mkdir()
        for content in ("private-value", "[]", json.dumps({"access_token": 42})):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid token file") as caught:
                    self.store.load()
                self.assertNotIn("private-value", str(caught.exception))

    def test_invalid_replacement_preserves_existing_token(self):
        self.store.save("old-token")
        for value in ("", " ", "bad\ntoken", "bad\x7ftoken"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.store.save(value)
                self.assertEqual(self.store.load(), "old-token")

    def test_failed_write_retains_saved_token_and_cleans_temporary_file(self):
        self.store.save("old-token")
        with patch(
            "monocloud_subscription.tokens.os.replace",
            side_effect=OSError("private-details"),
        ):
            with self.assertRaisesRegex(ValueError, "Cannot save token") as caught:
                self.store.save("new-token")
        self.assertNotIn("private-details", str(caught.exception))
        self.assertEqual(self.store.load(), "old-token")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
