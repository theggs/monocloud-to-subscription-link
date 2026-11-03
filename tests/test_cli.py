import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from monocloud_subscription.cli import main


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

    def test_external_web_binding_requires_management_password(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        with patch.dict(os.environ, {"MONOCLOUD_WEB_PASSWORD": ""}):
            result = self.run_cli(
                "--config", str(self.path), "serve", "--host", "0.0.0.0"
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("MONOCLOUD_WEB_PASSWORD", result.stderr)

    def test_web_serve_uses_configured_address_without_access_logs(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        with patch("uvicorn.run") as run:
            self.assertEqual(
                main(["--config", str(self.path), "serve", "--port", "8081"]), 0
            )
        self.assertEqual(
            run.call_args.kwargs,
            {"host": "127.0.0.1", "port": 8081, "access_log": False},
        )

    def test_remote_binding_warns_about_plaintext_credentials(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        output = io.StringIO()
        with (
            patch.dict(
                os.environ, {"MONOCLOUD_WEB_PASSWORD": "fake-management-password"}
            ),
            patch("uvicorn.run"),
            redirect_stderr(output),
        ):
            self.assertEqual(
                main(["--config", str(self.path), "serve", "--host", "0.0.0.0"]), 0
            )
        self.assertIn("http://0.0.0.0:8080", output.getvalue())
        self.assertIn("does not encrypt", output.getvalue())
        self.assertNotIn("fake-management-password", output.getvalue())

    def test_check_from_another_directory_is_read_only(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        result = self.run_cli("--config", str(self.path), "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Configuration OK", result.stdout)
        self.assertIn(str(self.directory / "data"), result.stdout)
        self.assertFalse((self.directory / "data").exists())

    def test_serve_normalizes_loopback_addresses_before_binding(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        for value, normalized, url in (
            (" [::1] ", "::1", "http://[::1]:8080"),
            (" 127.0.0.1 ", "127.0.0.1", "http://127.0.0.1:8080"),
        ):
            with self.subTest(host=value):
                output = io.StringIO()
                with (
                    patch.dict(os.environ, {"MONOCLOUD_WEB_PASSWORD": ""}),
                    patch("uvicorn.run") as run,
                    redirect_stderr(output),
                ):
                    self.assertEqual(
                        main(["--config", str(self.path), "serve", "--host", value]), 0
                    )
                self.assertEqual(run.call_args.kwargs["host"], normalized)
                self.assertIn(url, output.getvalue())
                self.assertNotIn("WARNING", output.getvalue())

    def test_serve_rejects_empty_host_before_binding(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        with (
            patch.dict(
                os.environ, {"MONOCLOUD_WEB_PASSWORD": "fake-management-password"}
            ),
            patch("uvicorn.run") as run,
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as caught:
                main(["--config", str(self.path), "serve", "--host", "  "])
        self.assertEqual(caught.exception.code, 2)
        run.assert_not_called()

    def test_serve_rejects_urls_ports_paths_and_unbalanced_ipv6(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        for value in (
            "example.com:8080",
            "127.0.0.1:8080",
            "[::1",
            "::1]",
            "https://example.invalid",
            "example.invalid/path",
        ):
            with self.subTest(host=value):
                output = io.StringIO()
                with (
                    patch.dict(
                        os.environ,
                        {"MONOCLOUD_WEB_PASSWORD": "fake-management-password"},
                    ),
                    patch("uvicorn.run") as run,
                    redirect_stderr(output),
                ):
                    with self.assertRaises(SystemExit) as caught:
                        main(["--config", str(self.path), "serve", "--host", value])
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(
                    "Host must be a hostname or IP address", output.getvalue()
                )
                run.assert_not_called()

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

    def test_serve_uses_toml_address_and_cli_overrides(self):
        self.path.write_text(
            'data_dir = "data"\n[server]\nhost = "localhost"\nport = 8090'
        )
        for arguments, host, port in (
            ([], "localhost", 8090),
            (["--host", "127.0.0.1", "--port", "8091"], "127.0.0.1", 8091),
        ):
            with patch("uvicorn.run") as run, redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(["--config", str(self.path), "serve", *arguments]), 0
                )
            self.assertEqual(run.call_args.kwargs["host"], host)
            self.assertEqual(run.call_args.kwargs["port"], port)

    def test_startup_explains_management_credential_source_without_password(self):
        self.path.write_text('data_dir = "data"')
        output = io.StringIO()
        with (
            patch.dict(
                os.environ, {"MONOCLOUD_WEB_PASSWORD": "constructed-private-password"}
            ),
            patch("uvicorn.run"),
            redirect_stderr(output),
        ):
            main(["--config", str(self.path), "serve"])
        text = output.getvalue()
        self.assertIn("username: admin", text)
        self.assertIn("MONOCLOUD_WEB_PASSWORD", text)
        self.assertNotIn("constructed-private-password", text)
