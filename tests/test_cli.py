import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import httpx

from monocloud_subscription.cli import main
from monocloud_subscription.tokens import TokenStore


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "config.toml"

    def run_cli(self, *args, input_text=None):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        return subprocess.run(
            [sys.executable, "-m", "monocloud_subscription.cli", *args],
            cwd=self.directory,
            env=environment,
            capture_output=True,
            text=True,
            input=input_text,
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

    def test_nodes_with_no_token_exits_before_network_access(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        result = self.run_cli("--config", str(self.path), "nodes", "--plan-id", "123")
        self.assertEqual(result.returncode, 2)
        self.assertIn("No saved token", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_login_without_client_settings_exits_before_prompting(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        result = self.run_cli("--config", str(self.path), "login")
        self.assertEqual(result.returncode, 2)
        self.assertIn("client_id", result.stderr)
        self.assertNotIn("Email:", result.stdout)

    def test_import_requires_hidden_terminal_input(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        result = self.run_cli(
            "--config", str(self.path), "import-token", input_text="must-not-store\n"
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.directory / "data" / "token.json").exists())
        self.assertNotIn("must-not-store", result.stdout + result.stderr)

    def test_login_saves_only_token_without_printing_secrets(self):
        self.path.write_text(
            """data_dir = "data"
[monocloud]
client_id = "test-client"
client_secret = "test-client-secret"
""",
            encoding="utf-8",
        )
        http = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"access_token": "test-new-token"}
                )
            )
        )
        output = io.StringIO()
        with (
            patch("builtins.input", return_value="user@example.invalid"),
            patch(
                "monocloud_subscription.cli.getpass.getpass",
                return_value="test-password",
            ),
            patch("monocloud_subscription.cli.httpx.Client", return_value=http),
            redirect_stdout(output),
        ):
            result = main(["--config", str(self.path), "login"])
        self.assertEqual(result, 0)
        token_path = self.directory / "data" / "token.json"
        self.assertEqual(TokenStore(token_path).load(), "test-new-token")
        self.assertNotIn("test-password", token_path.read_text())
        for value in ("test-password", "test-new-token", "test-client-secret"):
            self.assertNotIn(value, output.getvalue())

    def test_failed_login_retains_existing_token(self):
        self.path.write_text(
            """data_dir = "data"
[monocloud]
client_id = "test-client"
client_secret = "test-client-secret"
""",
            encoding="utf-8",
        )
        store = TokenStore(self.directory / "data" / "token.json")
        store.save("old-token")
        http = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, text="private-remote-error")
            )
        )
        output = io.StringIO()
        with (
            patch("builtins.input", return_value="user@example.invalid"),
            patch(
                "monocloud_subscription.cli.getpass.getpass",
                return_value="test-password",
            ),
            patch("monocloud_subscription.cli.httpx.Client", return_value=http),
            redirect_stderr(output),
        ):
            with self.assertRaises(SystemExit) as caught:
                main(["--config", str(self.path), "login"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(store.load(), "old-token")
        self.assertNotIn("private-remote-error", output.getvalue())

    def test_import_token_saves_without_echoing_value(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        output = io.StringIO()
        with (
            patch(
                "monocloud_subscription.cli.getpass.getpass",
                return_value="fake-imported-token",
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["--config", str(self.path), "import-token"]), 0)
        self.assertEqual(
            TokenStore(self.directory / "data/token.json").load(), "fake-imported-token"
        )
        self.assertNotIn("fake-imported-token", output.getvalue())

    def test_nodes_default_discovers_services_and_only_prints_count(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        store = TokenStore(self.directory / "data/token.json")
        store.save("fake-token")
        paths = []

        def handle(request):
            paths.append(request.url.path)
            if request.url.path == "/api/service":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 123,
                            "plan": {"name": "Example", "type": "shadowsocks"},
                        }
                    ],
                )
            return httpx.Response(
                200,
                json=[
                    {
                        "hostname": "node.example.invalid",
                        "port": 443,
                        "encryption": "chacha20-ietf-poly1305",
                        "password": "fake-node-password",
                    }
                ],
            )

        http = httpx.Client(transport=httpx.MockTransport(handle))
        output = io.StringIO()
        with (
            patch("monocloud_subscription.cli.httpx.Client", return_value=http),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["--config", str(self.path), "nodes"]), 0)
        self.assertEqual(paths, ["/api/service", "/api/shadowsocks/123"])
        self.assertIn("Fetched 1 available nodes", output.getvalue())
        for value in ("fake-token", "fake-node-password", "node.example.invalid"):
            self.assertNotIn(value, output.getvalue())

    def test_plans_reports_service_ids(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        TokenStore(self.directory / "data/token.json").save("fake-token")
        http = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=[
                        {
                            "id": 123,
                            "plan_id": 456,
                            "plan": {"name": "Example", "type": "shadowsocks"},
                        }
                    ],
                )
            )
        )
        output = io.StringIO()
        with (
            patch("monocloud_subscription.cli.httpx.Client", return_value=http),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["--config", str(self.path), "plans"]), 0)
        self.assertIn("123\tExample", output.getvalue())
        self.assertNotIn("456", output.getvalue())
