import json
import re
import tempfile
import unittest
from pathlib import Path

from monocloud_subscription.subscription_state import SubscriptionStore


class SubscriptionStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "subscription.json"

    def test_key_is_random_private_and_stable_and_toggle_survives_restart(self):
        store = SubscriptionStore(self.path)
        state = store.load()
        self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9_-]{43}", state.key))
        self.assertIsNone(state.tailscale_enabled)
        self.assertNotIn(state.key, repr(state))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(SubscriptionStore(self.path).load().key, state.key)
        store.set_enabled(True)
        self.assertEqual(SubscriptionStore(self.path).load().key, state.key)
        self.assertTrue(SubscriptionStore(self.path).load().tailscale_enabled)
        store.set_enabled(False)
        self.assertFalse(SubscriptionStore(self.path).load().tailscale_enabled)

    def test_corrupt_state_is_not_reset_and_errors_are_private(self):
        self.path.parent.mkdir()
        for text in (
            "private-state",
            "[]",
            '{"key":"private-key"}',
            json.dumps({"key": "x" * 43, "tailscale_enabled": "private-value"}),
        ):
            self.path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError) as caught:
                SubscriptionStore(self.path).load()
            self.assertEqual(self.path.read_text(), text)
            self.assertNotIn("private-", str(caught.exception))

    def test_save_failure_preserves_previous_state(self):
        from unittest.mock import patch

        store = SubscriptionStore(self.path)
        before = store.load()
        with patch(
            "monocloud_subscription.subscription_state.os.replace",
            side_effect=OSError("private-failure"),
        ):
            with self.assertRaises(ValueError) as caught:
                store.set_enabled(True)
        self.assertNotIn("private-failure", str(caught.exception))
        self.assertEqual(store.load(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
