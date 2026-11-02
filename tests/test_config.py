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

    def test_token_path_defaults_to_data_directory(self):
        self.path.write_text('data_dir = "data"', encoding="utf-8")
        config = load_config(self.path)
        self.assertEqual(config.token_file, self.directory / "data" / "token.json")

    def test_monocloud_settings_and_token_path_are_configurable(self):
        self.path.write_text(
            """data_dir = "data"
token_file = "credentials/session.json"
[monocloud]
client_id = "example-client"
client_secret = "example-secret"
client_version = "example-version"
user_agent = "example-agent"
""",
            encoding="utf-8",
        )
        config = load_config(self.path)
        self.assertEqual(config.token_file, self.directory / "credentials/session.json")
        self.assertEqual(config.monocloud.client_id, "example-client")
        self.assertEqual(config.monocloud.user_agent, "example-agent")
        self.assertNotIn("example-secret", repr(config))

    def test_invalid_settings_do_not_echo_values(self):
        for value in (
            'monocloud = "private-value"',
            "[monocloud]\nuser_agent = 42",
            '[monocloud]\nbase_url = "http://insecure.invalid"',
            '[monocloud]\nuser_agent = "bad\\nheader"',
        ):
            with self.subTest(value=value):
                self.path.write_text('data_dir = "data"\n' + value, encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    load_config(self.path)
                self.assertNotIn("private-value", str(caught.exception))

    def test_tailscale_is_optional_and_paths_belong_to_the_client(self):
        self.path.write_text('data_dir = "data"\n', encoding="utf-8")
        config = load_config(self.path)
        self.assertFalse(config.tailscale.enabled)
        self.assertEqual(config.clash.mixed_port, 7890)
        self.path.write_text(
            """data_dir = "data"
[clash]
mixed_port = 7891
[tailscale]
enabled = true
hostname = "example-phone"
state_dir = "client-state"
auth_key = "constructed-private-key"
routes = ["192.168.50.0/24", "fd00:1234::/64"]
""",
            encoding="utf-8",
        )
        config = load_config(self.path)
        self.assertTrue(config.tailscale.enabled)
        self.assertEqual(config.tailscale.state_dir, "client-state")
        self.assertEqual(config.tailscale.routes, ("192.168.50.0/24", "fd00:1234::/64"))
        self.assertEqual(config.clash.mixed_port, 7891)
        self.assertNotIn("constructed-private-key", repr(config))

    def test_invalid_generator_options_are_sanitized(self):
        for options in (
            "clash = false",
            "[clash]\nmixed_port = true",
            "[clash]\nmixed_port = 65536",
            'tailscale = "private-value"',
            '[tailscale]\nenabled = "true"',
            '[tailscale]\nstate_dir = ""',
            "[tailscale]\nauth_key = 123",
            '[tailscale]\nroutes = ["private-value"]',
            '[tailscale]\nroutes = ["0.0.0.0/0"]',
            '[tailscale]\ncontrol_url = "http://private-value"',
        ):
            with self.subTest(options=options):
                self.path.write_text('data_dir = "data"\n' + options, encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    load_config(self.path)
                self.assertNotIn("private-value", str(caught.exception))

    def test_server_subscription_and_template_paths(self):
        self.path.write_text(
            """data_dir = "data"
template_dir = "official-snapshot"
[server]
host = "0.0.0.0"
port = 8090
public_url = "https://example.invalid/mono"
[subscription]
key = "constructed-url-key-01234567890123456789"
""",
            encoding="utf-8",
        )
        config = load_config(self.path)
        self.assertEqual(config.server.host, "0.0.0.0")
        self.assertEqual(config.server.port, 8090)
        self.assertEqual(config.server.public_url, "https://example.invalid/mono")
        self.assertEqual(config.template_dir, self.directory / "official-snapshot")
        self.assertNotIn("constructed-url-key", repr(config))
        self.assertFalse(config.data_dir.exists())

    def test_invalid_web_service_options_do_not_echo_private_data(self):
        for text in (
            "template_dir = 1",
            "server = false",
            "[server]\nport = true",
            "[server]\nport = 65536",
            '[server]\nhost = ""',
            '[server]\npublic_url = "https://private-value@example.invalid"',
            '[server]\npublic_url = "http://example.invalid/?private-value"',
            "subscription = false",
            '[subscription]\nkey = "private-value"',
        ):
            self.path.write_text('data_dir = "data"\n' + text)
            with self.subTest(text=text), self.assertRaises(ValueError) as caught:
                load_config(self.path)
            self.assertNotIn("private-value", str(caught.exception))
