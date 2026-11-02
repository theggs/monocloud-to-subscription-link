import tempfile
import unittest
from pathlib import Path

from monocloud_subscription.config import load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.path = self.directory / "config.toml"

    def test_relative_data_directory_is_relative_to_config(self):
        self.path.write_text('data_dir = "data"\n', encoding="utf-8")
        config = load_config(self.path)
        self.assertEqual(config.data_dir, self.directory / "data")
        self.assertFalse(config.data_dir.exists())

    def test_absolute_data_directory_is_preserved(self):
        target = self.directory / "state"
        self.path.write_text(f'data_dir = "{target.as_posix()}"\n', encoding="utf-8")
        self.assertEqual(load_config(self.path).data_dir, target)

    def test_missing_empty_and_non_string_data_directory_are_rejected(self):
        for content in ("", 'data_dir = ""', 'data_dir = "  "', "data_dir = 42"):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "data_dir"):
                    load_config(self.path)

    def test_malformed_toml_does_not_echo_contents(self):
        self.path.write_text("private-secret = [invalid", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid TOML configuration") as caught:
            load_config(self.path)
        self.assertNotIn("private-secret", str(caught.exception))

    def test_missing_configuration_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Cannot read configuration"):
            load_config(self.path)
