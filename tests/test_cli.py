import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "config.toml"

    def run_cli(self, *args):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        return subprocess.run(
            [sys.executable, "-m", "monocloud_subscription.cli", *args],
            cwd=self.directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_help_does_not_require_configuration(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check", result.stdout)

    def test_check_from_another_directory_is_read_only(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        result = self.run_cli("--config", str(self.path), "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Configuration OK", result.stdout)
        self.assertIn(str(self.directory / "data"), result.stdout)
        self.assertFalse((self.directory / "data").exists())

    def test_invalid_config_returns_a_concise_error(self):
        self.path.write_text("secret-value = [invalid", encoding="utf-8")
        result = self.run_cli("--config", str(self.path), "check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid TOML configuration", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("secret-value", result.stderr)

    def test_check_requires_an_explicit_config_path(self):
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--config is required", result.stderr)
