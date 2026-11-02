import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_clash import TEMPLATE

from monocloud_subscription.templates import load_template_snapshot


class SnapshotTests(unittest.TestCase):
    def test_official_snapshot_uses_same_integrity_checks_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "templates": [
                    {
                        "name": "Clash_ss",
                        "url": "https://static.example.invalid/Clash_ss",
                        "size": len(TEMPLATE),
                        "sha256": hashlib.sha256(TEMPLATE).hexdigest(),
                    }
                ]
            }
            (root / "update.json").write_text(json.dumps(manifest))
            (root / "Clash_ss").write_bytes(TEMPLATE)
            self.assertEqual(load_template_snapshot(root)["rules"][-1], "MATCH,Proxy")
            (root / "Clash_ss").write_bytes(TEMPLATE + b"\n")
            with self.assertRaises(ValueError):
                load_template_snapshot(root)
            (root / "update.json").write_text("private-invalid-manifest")
            with self.assertRaises(ValueError) as caught:
                load_template_snapshot(root)
            self.assertNotIn("private-invalid", str(caught.exception))

    def test_missing_snapshot_has_sanitized_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_template_snapshot(Path(directory))
