"""Exercise the actual HTTP transport against a local server with fake data."""

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from monocloud_subscription.monocloud import (
    AuthenticationError,
    MonoCloudClient,
    MonoCloudSettings,
)
from monocloud_subscription.tokens import TokenStore


class FakeMonoCloudHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        self.server.requests.append(("POST", self.path))
        form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        expected = {
            "grant_type": ["password"],
            "username": ["user@example.invalid"],
            "password": ["fake-account-password"],
            "client_id": ["fake-client"],
            "client_secret": ["fake-client-secret"],
        }
        if self.path == "/oauth/token" and form == expected:
            self.respond(200, {"access_token": "fake-access-token"})
        else:
            self.respond(400, {"message": "fake-server-private-error"})

    def do_GET(self):
        self.server.requests.append(("GET", self.path))
        if self.headers.get("Authorization") != "Bearer fake-access-token":
            self.respond(401, {"message": "fake-server-private-error"})
        elif self.path == "/api/service":
            self.respond(
                200,
                [
                    {
                        "id": 123,
                        "plan_id": 456,
                        "plan": {"id": 456, "name": "Example", "type": "shadowsocks"},
                    }
                ],
            )
        elif self.path == "/api/shadowsocks/123":
            self.respond(
                200,
                [
                    {
                        "hostname": "node.example.invalid",
                        "port": 443,
                        "encryption": "chacha20-ietf-poly1305",
                        "password": "fake-node-password",
                        "alias": "Example node",
                        "enable": 1,
                    }
                ],
            )
        else:
            self.respond(404, {})


class HttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMonoCloudHandler)
        self.server.requests = []
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()
        self.addCleanup(self.stop_server)
        # Only this in-process fixture uses HTTP. User configuration still requires HTTPS.
        self.settings = MonoCloudSettings(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            client_id="fake-client",
            client_secret="fake-client-secret",
        )

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_login_save_reuse_and_discover_nodes_over_real_http(self):
        store = TokenStore(Path(self.temp.name) / "state" / "token.json")
        with httpx.Client(trust_env=False) as http:
            api = MonoCloudClient(self.settings, http)
            store.save(api.login("user@example.invalid", "fake-account-password"))
            nodes = api.fetch_all_nodes(store.load())
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].plan_id, "123")
        self.assertEqual(nodes[0].password, "fake-node-password")
        self.assertEqual(
            self.server.requests,
            [
                ("POST", "/oauth/token"),
                ("GET", "/api/service"),
                ("GET", "/api/shadowsocks/123"),
            ],
        )

    def test_rejected_token_stops_after_one_real_http_request(self):
        with httpx.Client(trust_env=False) as http:
            api = MonoCloudClient(self.settings, http)
            with self.assertRaises(AuthenticationError) as caught:
                api.fetch_all_nodes("fake-expired-token")
        self.assertEqual(self.server.requests, [("GET", "/api/service")])
        self.assertNotIn("fake-server-private-error", str(caught.exception))
