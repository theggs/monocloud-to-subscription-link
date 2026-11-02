import hashlib
import tempfile
import unittest
from pathlib import Path

import httpx
import yaml
from test_clash import TEMPLATE

from monocloud_subscription.config import Config
from monocloud_subscription.subscription import generate_subscription
from monocloud_subscription.tokens import TokenStore


class SubscriptionTests(unittest.TestCase):
    def test_saved_token_all_services_template_and_generation(self):
        seen = []

        def handle(request):
            seen.append(request.url.path)
            if request.url.path.startswith("/api/"):
                self.assertEqual(
                    request.headers["Authorization"], "Bearer constructed-token"
                )
            else:
                self.assertNotIn("Authorization", request.headers)
            if request.url.path == "/api/service":
                return httpx.Response(
                    200,
                    json=[
                        {"id": i, "plan": {"name": "Example", "type": "shadowsocks"}}
                        for i in (1, 2)
                    ],
                )
            if request.url.path.startswith("/api/shadowsocks/"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "alias": "Same",
                            "hostname": "example.invalid",
                            "port": 443,
                            "encryption": "aes-128-gcm",
                            "password": "constructed-password",
                        }
                    ],
                )
            if request.url.path.endswith("update.json"):
                return httpx.Response(
                    200,
                    json={
                        "templates": [
                            {
                                "name": "Clash_ss",
                                "url": "https://static.example.invalid/Clash_ss",
                                "size": len(TEMPLATE),
                                "sha256": hashlib.sha256(TEMPLATE).hexdigest(),
                            }
                        ]
                    },
                )
            return httpx.Response(200, content=TEMPLATE)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Config(root, root / "token.json")
            TokenStore(config.token_file).save("constructed-token")
            before = config.token_file.read_bytes()
            with httpx.Client(transport=httpx.MockTransport(handle)) as http:
                result = yaml.safe_load(generate_subscription(config, http))
            self.assertEqual(len(result["proxies"]), 2)
            self.assertEqual(before, config.token_file.read_bytes())
            self.assertIn("/api/shadowsocks/1", seen)
            self.assertIn("/api/shadowsocks/2", seen)

    def test_missing_token_or_failed_discovery_does_not_produce_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Config(root, root / "token.json")
            with httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(401))
            ) as http:
                with self.assertRaises(ValueError):
                    generate_subscription(config, http)
                TokenStore(config.token_file).save("old-token")
                with self.assertRaises(ValueError):
                    generate_subscription(config, http)
                self.assertEqual(TokenStore(config.token_file).load(), "old-token")
