import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monocloud_subscription.tokens import TokenStore


class TokenTests(unittest.TestCase):
    def test_oversized_expiry_is_reported_as_invalid_storage(self):
        self.path.parent.mkdir()
        self.path.write_text(
            json.dumps({"access_token": "synthetic-token", "expires_at": 10**400})
        )
        with self.assertRaisesRegex(ValueError, "Invalid token file"):
            self.store.load_session()

    def test_refresh_state_round_trip_and_old_file_compatibility(self):
        from monocloud_subscription.tokens import Session

        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(Path(directory) / "token.json")
            store.save("legacy-access")
            self.assertIsNone(store.load_session().refresh_token)
            session = Session("new-access", "new-refresh", 1800000000)
            store.save_session(session)
            self.assertEqual(store.load_session(), session)
            self.assertEqual(store.load(), "new-access")

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
