"""Constructed MonoCloud v2 protocol fixtures; no real account data."""

import base64
import hashlib
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from test_clash import TEMPLATE

from monocloud_subscription.config import Config
from monocloud_subscription.monocloud import (
    AuthenticationError,
    MonoCloudClient,
    MonoCloudError,
    MonoCloudSettings,
)
from monocloud_subscription.subscription import generate_subscription
from monocloud_subscription.tokens import TokenStore

SHARED_KEY = bytes(range(32))
KEY_ID = "synthetic-key-id"
SERVICES = [
    {
        "id": 123,
        "status": "active",
        "connectable": True,
        "expires_at": "2027-01-01",
        "days_remaining": 44,
        "suspension": None,
        "plan": {"name": "Example plan"},
        "category": {"name": "Example"},
        "usage": {
            "upload_bytes": 0,
            "download_bytes": 0,
            "allowance_bytes": None,
            "resets_on": None,
        },
    },
    {
        "id": 456,
        "status": "suspended",
        "connectable": False,
        "plan": {"name": "Unavailable"},
    },
]
SERVER = {
    "id": 7,
    "protocol": "shadowsocks",
    "alias": "Example node",
    "group": None,
    "emoji": None,
    "location": None,
    "host": "node.example.invalid",
    "port": 443,
    "udp_port": None,
    "udp_port_range": None,
    "params": {"method": "aes-128-gcm"},
    "auth": {
        "password": "synthetic-node-password",
        "username": "",
        "server_key": "",
        "user_key": "",
    },
}


def encoded(value):
    return base64.b64encode(value).decode()


def encrypted_reply(request, data):
    """Independent fixture implements the observed wire construction."""
    client_public = base64.b64decode(request.headers["X-Response-Public-Key"])
    private = X25519PrivateKey.from_private_bytes(bytes(range(32, 64)))
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SHARED_KEY,
        info=b"monocloud server list v1" + client_public + public,
    ).derive(private.exchange(X25519PublicKey.from_public_bytes(client_public)))
    nonce = bytes(range(12))
    ciphertext = AESGCM(key).encrypt(nonce, json.dumps(data).encode(), None)
    return {
        "encryption": "x25519-hkdf-sha256-aes-256-gcm",
        "key_id": KEY_ID,
        "public_key": encoded(public),
        "nonce": encoded(nonce),
        "ciphertext": encoded(ciphertext),
    }


class V2Tests(unittest.TestCase):
    def test_subscription_generation_uses_the_saved_refresh_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = TokenStore(root / "token.json")
            store.path.write_text(
                json.dumps(
                    {
                        "access_token": "old-access",
                        "refresh_token": "old-refresh",
                        "expires_at": 1,
                    }
                )
            )

            def handler(request):
                if request.url.path == "/oauth/token":
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "new-access",
                            "refresh_token": "new-refresh",
                            "expires_in": 3600,
                        },
                    )
                if request.url.path == "/api/v2/services":
                    self.assertEqual(
                        request.headers["Authorization"], "Bearer new-access"
                    )
                    return httpx.Response(200, json={"data": SERVICES})
                if request.url.path == "/api/v2/servers":
                    self.assertEqual(
                        request.headers["Authorization"], "Bearer new-access"
                    )
                    return httpx.Response(
                        200,
                        json={
                            "data": encrypted_reply(
                                request,
                                [
                                    {
                                        "service_id": 123,
                                        "servers": [
                                            {"protocol": "monolite"},
                                            SERVER,
                                            {"protocol": "papaya"},
                                        ],
                                    }
                                ],
                            )
                        },
                    )
                if request.url.path.endswith("update.json"):
                    self.assertNotIn("Authorization", request.headers)
                    return httpx.Response(200, json={"templates": [{"name": "Other"}]})
                self.assertEqual(
                    str(request.url), "https://static.monocloud.co/mono_go/Clash_ss"
                )
                self.assertNotIn("Authorization", request.headers)
                return httpx.Response(200, content=TEMPLATE)

            settings = self.settings(
                response_key_id=KEY_ID, response_key=encoded(SHARED_KEY)
            )
            config = Config(root, store.path, monocloud=settings)
            with (
                patch(
                    "monocloud_subscription.templates._PINNED_CLASH_TEMPLATE",
                    {
                        "url": "https://static.monocloud.co/mono_go/Clash_ss",
                        "size": len(TEMPLATE),
                        "sha256": hashlib.sha256(TEMPLATE).hexdigest(),
                    },
                ),
                httpx.Client(transport=httpx.MockTransport(handler)) as http,
            ):
                result = yaml.safe_load(generate_subscription(config, http))
            self.assertEqual(len(result["proxies"]), 1)
            self.assertEqual(
                result["proxies"][0]["password"], "synthetic-node-password"
            )
            self.assertEqual(store.load_session().refresh_token, "new-refresh")

    def settings(self, **options):
        return MonoCloudSettings(
            client_id="synthetic-client",
            client_secret="synthetic-client-secret",
            **options,
        )

    def client(self, handler, **options):
        http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http.close)
        return MonoCloudClient(self.settings(**options), http)

    def test_v2_catalog_maps_services_and_requests_servers_once(self):
        paths = []

        def handler(request):
            paths.append(request.url.path)
            if request.url.path == "/api/v2/services":
                return httpx.Response(200, json={"data": SERVICES, "meta": {}})
            self.assertEqual(request.url.path, "/api/v2/servers")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"service_id": 123, "servers": [SERVER]},
                        {"service_id": 999, "servers": [SERVER]},
                    ],
                    "meta": {"servers_version": "synthetic-version"},
                },
            )

        api = self.client(handler)
        nodes = api.fetch_all_nodes("synthetic-token")
        self.assertEqual(paths, ["/api/v2/services", "/api/v2/servers"])
        self.assertEqual(len(nodes), 1)
        self.assertEqual(
            (nodes[0].service_id, nodes[0].server, nodes[0].cipher),
            ("123", "node.example.invalid", "aes-128-gcm"),
        )
        self.assertNotIn("synthetic-node-password", repr(nodes))

    def test_encrypted_servers_are_decrypted_with_ephemeral_key(self):
        publics = []

        def handler(request):
            self.assertEqual(request.headers["X-Response-Key-Id"], KEY_ID)
            publics.append(request.headers["X-Response-Public-Key"])
            return httpx.Response(
                200,
                json={
                    "data": encrypted_reply(
                        request,
                        [
                            {"service_id": 123, "servers": [SERVER]},
                        ],
                    ),
                    "meta": {},
                },
            )

        api = self.client(
            handler, response_key_id=KEY_ID, response_key=encoded(SHARED_KEY)
        )
        for _ in range(2):
            nodes = api.fetch_nodes("synthetic-token", "123")
            self.assertEqual(nodes[0].password, "synthetic-node-password")
        self.assertNotEqual(publics[0], publics[1])

    def test_encryption_failures_and_plaintext_downgrade_fail_closed(self):
        for mutation in ("key_id", "public_key", "nonce", "ciphertext", "plaintext"):
            with self.subTest(mutation=mutation):

                def handler(request):
                    data = encrypted_reply(
                        request, [{"service_id": 123, "servers": [SERVER]}]
                    )
                    if mutation == "plaintext":
                        data = [{"service_id": 123, "servers": [SERVER]}]
                    elif mutation == "key_id":
                        data[mutation] = "different-key"
                    elif mutation == "ciphertext":
                        raw = bytearray(base64.b64decode(data[mutation]))
                        raw[-1] ^= 1
                        data[mutation] = encoded(raw)
                    else:
                        data[mutation] = "not-valid-base64!"
                    return httpx.Response(200, json={"data": data, "meta": {}})

                api = self.client(
                    handler, response_key_id=KEY_ID, response_key=encoded(SHARED_KEY)
                )
                with self.assertRaises(MonoCloudError) as caught:
                    api.fetch_nodes("synthetic-token", "123")
                self.assertNotIn("synthetic-node-password", str(caught.exception))

    def test_unsupported_node_options_are_not_silently_discarded(self):
        for update in (
            {"protocol": None},
            {"udp_port": 8443},
            {"auth": {**SERVER["auth"], "server_key": "unsupported-key"}},
            {"port": True},
            {"params": {"method": "unknown-cipher"}},
            {"params": {"method": "aes-128-gcm", "plugin": "not-supported"}},
        ):
            with self.subTest(update=update):
                api = self.client(
                    lambda r: httpx.Response(
                        200,
                        json={
                            "data": [
                                {"service_id": 123, "servers": [{**SERVER, **update}]},
                            ]
                        },
                    )
                )
                with self.assertRaises(MonoCloudError):
                    api.fetch_nodes("synthetic-token", "123")

    def test_login_returns_refreshable_session_without_secret_repr(self):
        api = self.client(
            lambda r: httpx.Response(
                200,
                json={
                    "access_token": "synthetic-access",
                    "refresh_token": "synthetic-refresh",
                    "expires_in": 3600,
                },
            )
        )
        before = time.time()
        session = api.login_session("user@example.invalid", "synthetic-password")
        self.assertEqual(session.access_token, "synthetic-access")
        self.assertEqual(session.refresh_token, "synthetic-refresh")
        self.assertGreaterEqual(session.expires_at, before + 3600)
        self.assertNotIn("synthetic-access", repr(session))
        self.assertNotIn("synthetic-refresh", repr(session))

    def test_v2_node_accepts_bare_hosts_and_rejects_malformed_addresses(self):
        for host in (
            "https://node.example.invalid/path",
            "node.example.invalid:443",
            "node\x00.example.invalid",
            "[2001:db8::1]",
        ):
            with self.subTest(host=host), self.assertRaises(MonoCloudError):
                MonoCloudClient._v2_node({**SERVER, "host": host}, "123", 1)

        for host, expected in (
            ("node.example.invalid.", "node.example.invalid."),
            ("192.0.2.1", "192.0.2.1"),
            ("2001:db8::1", "2001:db8::1"),
            ("bücher.example.invalid", "xn--bcher-kva.example.invalid"),
        ):
            with self.subTest(host=host):
                node = MonoCloudClient._v2_node({**SERVER, "host": host}, "123", 1)
                self.assertEqual(node.server, expected)

    def test_ss2022_requires_valid_base64_psk_lengths(self):
        for password in ("ordinary-password", encoded(bytes(15)), encoded(bytes(32))):
            with self.subTest(password_length=len(password)):
                server = {
                    **SERVER,
                    "params": {"method": "2022-blake3-aes-128-gcm"},
                    "auth": {**SERVER["auth"], "password": password},
                }
                api = self.client(
                    lambda r: httpx.Response(
                        200, json={"data": [{"service_id": 123, "servers": [server]}]}
                    )
                )
                with self.assertRaises(MonoCloudError):
                    api.fetch_nodes("synthetic-token", "123")
        password = encoded(bytes(range(16)))
        server = {
            **SERVER,
            "params": {"method": "2022-blake3-aes-128-gcm"},
            "auth": {**SERVER["auth"], "password": password},
        }
        api = self.client(
            lambda r: httpx.Response(
                200, json={"data": [{"service_id": 123, "servers": [server]}]}
            )
        )
        self.assertEqual(
            api.fetch_nodes("synthetic-token", "123")[0].password, password
        )

    def test_expired_token_is_rotated_and_persisted_before_catalog_request(self):
        self.check_rotation(expired=True)

    def test_one_401_refreshes_and_replays_the_read_once(self):
        self.check_rotation(expired=False)

    def check_rotation(self, *, expired):
        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(Path(directory) / "token.json")
            store.path.write_text(
                json.dumps(
                    {
                        "access_token": "old-access",
                        "refresh_token": "old-refresh",
                        "expires_at": 1 if expired else time.time() + 3600,
                    }
                )
            )
            seen = []

            def handler(request):
                seen.append(request.url.path)
                if request.url.path == "/oauth/token":
                    self.assertEqual(
                        parse_qs(request.content.decode())["refresh_token"],
                        ["old-refresh"],
                    )
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "new-access",
                            "refresh_token": "new-refresh",
                            "expires_in": 3600,
                        },
                    )
                if request.headers["Authorization"] == "Bearer old-access":
                    return httpx.Response(401, json={"error": "token_expired"})
                self.assertEqual(store.load(), "new-access")
                return httpx.Response(200, json={"data": SERVICES})

            http = httpx.Client(transport=httpx.MockTransport(handler))
            with http:
                api = MonoCloudClient(self.settings(), http, token_store=store)
                self.assertEqual(api.fetch_plans("old-access")[0].name, "Example plan")
            self.assertEqual(store.load_session().refresh_token, "new-refresh")
            self.assertEqual(seen.count("/oauth/token"), 1)
            self.assertEqual(seen.count("/api/v2/services"), 1 if expired else 2)

    def test_revoked_session_and_forbidden_response_do_not_refresh(self):
        for status, code in [
            (401, "signed_out_from_device"),
            (401, "signed_out_from_website"),
            (403, "forbidden"),
        ]:
            with (
                self.subTest(status=status, code=code),
                tempfile.TemporaryDirectory() as directory,
            ):
                store = TokenStore(Path(directory) / "token.json")
                store.path.write_text(
                    json.dumps(
                        {"access_token": "old-access", "refresh_token": "old-refresh"}
                    )
                )
                paths = []

                def handler(request):
                    paths.append(request.url.path)
                    return httpx.Response(
                        status, json={"error": code, "message": "private-details"}
                    )

                with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                    api = MonoCloudClient(self.settings(), http, token_store=store)
                    with self.assertRaises(AuthenticationError) as caught:
                        api.fetch_plans("old-access")
                self.assertEqual(paths, ["/api/v2/services"])
                self.assertNotIn("private-details", str(caught.exception))

    def test_concurrent_clients_share_one_rotating_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            path.write_text(
                json.dumps(
                    {
                        "access_token": "old-access",
                        "refresh_token": "old-refresh",
                        "expires_at": 1,
                    }
                )
            )
            count = 0
            count_lock = threading.Lock()

            def handler(request):
                nonlocal count
                if request.url.path == "/oauth/token":
                    with count_lock:
                        count += 1
                    time.sleep(0.01)
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "new-access",
                            "refresh_token": "new-refresh",
                            "expires_in": 3600,
                        },
                    )
                self.assertEqual(request.headers["Authorization"], "Bearer new-access")
                return httpx.Response(200, json={"data": SERVICES})

            def read(_):
                with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                    return MonoCloudClient(
                        self.settings(), http, token_store=TokenStore(path)
                    ).fetch_plans("old-access")

            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertTrue(all(list(pool.map(read, range(4)))))
            self.assertEqual(count, 1)

    def test_preemptive_refresh_is_not_repeated_after_another_401(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(Path(directory) / "token.json")
            store.path.write_text(
                json.dumps(
                    {
                        "access_token": "old-access",
                        "refresh_token": "old-refresh",
                        "expires_at": 1,
                    }
                )
            )
            paths = []

            def handler(request):
                paths.append(request.url.path)
                if request.url.path == "/oauth/token":
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "new-access",
                            "refresh_token": "new-refresh",
                            "expires_in": 3600,
                        },
                    )
                return httpx.Response(401, json={"error": "token_expired"})

            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                api = MonoCloudClient(self.settings(), http, token_store=store)
                with self.assertRaises(AuthenticationError):
                    api.fetch_plans("old-access")
            self.assertEqual(paths, ["/oauth/token", "/api/v2/services"])

    def test_rejected_refresh_persists_reauthentication_and_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(Path(directory) / "token.json")
            original = json.dumps(
                {
                    "access_token": "old-access",
                    "refresh_token": "old-refresh",
                    "expires_at": 1,
                }
            )
            store.path.write_text(original)
            paths = []

            def handler(request):
                paths.append(request.url.path)
                return httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "message": "private-server-details",
                    },
                )

            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                api = MonoCloudClient(self.settings(), http, token_store=store)
                with self.assertRaises(AuthenticationError):
                    api.fetch_plans("old-access")
                # A fresh client/store represents the next request after a restart.
                api = MonoCloudClient(
                    self.settings(), http, token_store=TokenStore(store.path)
                )
                with self.assertRaises(AuthenticationError):
                    api.fetch_plans("old-access")
            self.assertEqual(paths, ["/oauth/token"])
            self.assertEqual(
                json.loads(store.path.read_text()), {"reauth_required": True}
            )

    def test_confirmed_revocation_is_terminal_until_successful_login(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(Path(directory) / "token.json")
            store.path.write_text(
                json.dumps(
                    {"access_token": "old-access", "refresh_token": "old-refresh"}
                )
            )
            paths = []

            def handler(request):
                paths.append(request.url.path)
                if request.headers["Authorization"] == "Bearer old-access":
                    return httpx.Response(401, json={"error": "signed_out_from_device"})
                return httpx.Response(200, json={"data": SERVICES})

            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                for _ in range(2):
                    with self.assertRaises(AuthenticationError):
                        MonoCloudClient(
                            self.settings(), http, token_store=TokenStore(store.path)
                        ).fetch_plans("old-access")
                self.assertEqual(paths, ["/api/v2/services"])
                self.assertEqual(
                    json.loads(store.path.read_text()), {"reauth_required": True}
                )
                store.save("new-access")
                self.assertEqual(
                    MonoCloudClient(self.settings(), http, token_store=store)
                    .fetch_plans("new-access")[0]
                    .service_id,
                    "123",
                )

    def test_sign_in_limit_is_terminal_in_either_error_or_reason(self):
        for body in (
            {"error": "invalid_token", "reason": "sign_in_limit"},
            {"error": "sign_in_limit"},
        ):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                store = TokenStore(Path(directory) / "token.json")
                store.path.write_text(
                    json.dumps(
                        {"access_token": "old-access", "refresh_token": "old-refresh"}
                    )
                )
                paths = []

                def handler(request):
                    paths.append(request.url.path)
                    return httpx.Response(401, json=body)

                with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                    for _ in range(2):
                        with self.assertRaises(AuthenticationError):
                            MonoCloudClient(
                                self.settings(),
                                http,
                                token_store=TokenStore(store.path),
                            ).fetch_plans("old-access")
                self.assertEqual(paths, ["/api/v2/services"])
                self.assertEqual(
                    json.loads(store.path.read_text()), {"reauth_required": True}
                )

    def test_revocation_reason_takes_priority_over_invalid_token_code(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(Path(directory) / "token.json")
            store.path.write_text(
                json.dumps(
                    {"access_token": "old-access", "refresh_token": "old-refresh"}
                )
            )
            paths = []

            def handler(request):
                paths.append(request.url.path)
                return httpx.Response(
                    401,
                    json={
                        "error": "invalid_token",
                        "reason": "signed_out_from_website",
                    },
                )

            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                with self.assertRaises(AuthenticationError):
                    MonoCloudClient(
                        self.settings(), http, token_store=store
                    ).fetch_plans("old-access")
            self.assertEqual(paths, ["/api/v2/services"])
