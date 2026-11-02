import unittest
from urllib.parse import parse_qs

import httpx

from monocloud_subscription.monocloud import (
    AuthenticationError,
    MonoCloudClient,
    MonoCloudError,
    MonoCloudSettings,
)


class MonoCloudTests(unittest.TestCase):
    def client(self, response):
        self.requests = []

        def handle(request):
            self.requests.append(request)
            if isinstance(response, Exception):
                raise response
            return response

        http = httpx.Client(transport=httpx.MockTransport(handle))
        self.addCleanup(http.close)
        settings = MonoCloudSettings(
            client_id="test-client",
            client_secret="test-client-secret",
            client_version="test-version",
            user_agent="test-agent",
        )
        return MonoCloudClient(settings, http)

    def test_login_sends_confirmed_form_fields(self):
        api = self.client(httpx.Response(200, json={"access_token": "test-token"}))
        self.assertEqual(
            api.login("user@example.invalid", "test-password"), "test-token"
        )
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/oauth/token")
        self.assertEqual(
            parse_qs(request.content.decode()),
            {
                "grant_type": ["password"],
                "username": ["user@example.invalid"],
                "password": ["test-password"],
                "client_id": ["test-client"],
                "client_secret": ["test-client-secret"],
            },
        )

    def test_fetch_maps_nodes_and_skips_disabled_entries(self):
        # Constructed values matching the remotely confirmed array and field types.
        node = {
            "hostname": "node.example.invalid",
            "port": 443,
            "encryption": "chacha20-ietf-poly1305",
            "password": "test-node-secret",
            "alias": "Example",
            "enable": True,
        }
        api = self.client(httpx.Response(200, json=[node, {"enable": False}]))
        nodes = api.fetch_nodes("test-token", "123")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].server, "node.example.invalid")
        self.assertEqual(nodes[0].port, 443)
        self.assertEqual(nodes[0].cipher, "chacha20-ietf-poly1305")
        self.assertEqual(nodes[0].password, "test-node-secret")
        self.assertEqual(nodes[0].name, "Example")
        self.assertEqual(nodes[0].plan_id, "123")
        self.assertNotIn("test-node-secret", repr(nodes[0]))
        self.assertNotIn("test-client-secret", repr(api.settings))
        request = self.requests[0]
        self.assertEqual(request.url.path, "/api/shadowsocks/123")
        self.assertEqual(request.headers["authorization"], "Bearer test-token")
        self.assertEqual(request.headers["x-client-version"], "test-version")
        self.assertEqual(request.headers["user-agent"], "test-agent")

    def test_authentication_failure_is_not_retried_or_leaked(self):
        for status in (401, 403):
            with self.subTest(status=status):
                api = self.client(httpx.Response(status, text="remote-private-value"))
                with self.assertRaisesRegex(
                    AuthenticationError, "web interface"
                ) as caught:
                    api.fetch_nodes("test-token", "123")
                self.assertEqual(len(self.requests), 1)
                self.assertNotIn("remote-private-value", str(caught.exception))

    def test_failed_login_is_actionable(self):
        api = self.client(httpx.Response(400, json={"message": "private-response"}))
        with self.assertRaisesRegex(AuthenticationError, "web interface"):
            api.login("user@example.invalid", "test-password")
        self.assertEqual(len(self.requests), 1)

    def test_remote_errors_and_redirects_do_not_expose_body(self):
        for status in (302, 500):
            with self.subTest(status=status):
                api = self.client(
                    httpx.Response(
                        status,
                        text="remote-private-value",
                        headers={"Location": "https://other.invalid"},
                    )
                )
                with self.assertRaises(MonoCloudError) as caught:
                    api.fetch_nodes("test-token", "123")
                self.assertNotIn("remote-private-value", str(caught.exception))
                self.assertEqual(len(self.requests), 1)

    def test_invalid_json_or_node_shape_is_rejected(self):
        for response in (
            httpx.Response(200, text="private-non-json"),
            httpx.Response(200, json={"unknown": []}),
            httpx.Response(200, json=[{"password": "test-node-secret"}]),
        ):
            with self.subTest(response=response):
                api = self.client(response)
                with self.assertRaises(MonoCloudError) as caught:
                    api.fetch_nodes("test-token", "123")
                self.assertNotIn("test-node-secret", str(caught.exception))

    def test_login_rejects_missing_token(self):
        api = self.client(httpx.Response(200, json={"message": "private-response"}))
        with self.assertRaisesRegex(MonoCloudError, "access token"):
            api.login("user@example.invalid", "test-password")

    def test_network_errors_do_not_expose_request_details(self):
        api = self.client(httpx.ConnectError("private-network-details"))
        with self.assertRaisesRegex(MonoCloudError, "network request failed") as caught:
            api.fetch_nodes("test-token", "123")
        self.assertNotIn("private-network-details", str(caught.exception))

    def test_fetch_plans_uses_service_id_not_product_plan_id(self):
        api = self.client(
            httpx.Response(
                200,
                json=[
                    {
                        "id": 123,
                        "plan_id": 456,
                        "expire_days": 30,
                        "plan": {
                            "id": 456,
                            "name": "Example plan",
                            "type": "shadowsocks",
                        },
                    },
                    {"id": 789, "plan": {"name": "Other protocol", "type": "vpn"}},
                ],
            )
        )
        plans = api.fetch_plans("test-token")
        self.assertEqual(
            [(plan.id, plan.name) for plan in plans], [("123", "Example plan")]
        )
        self.assertEqual(self.requests[0].url.path, "/api/service")

    def test_fetch_plans_rejects_invalid_response(self):
        for value in (
            {"data": []},
            [None],
            [{"id": True, "plan": {"type": "shadowsocks"}}],
        ):
            with self.subTest(value=value):
                api = self.client(httpx.Response(200, json=value))
                with self.assertRaises(MonoCloudError):
                    api.fetch_plans("test-token")

    def test_fetch_all_nodes_discovers_services_and_queries_each(self):
        paths = []

        def handle(request):
            paths.append(request.url.path)
            self.assertEqual(request.headers["user-agent"], "MonocloudGO-1.0.1")
            self.assertEqual(request.headers["x-client-version"], "1.0.1")
            if request.url.path == "/api/service":
                return httpx.Response(
                    200,
                    json=[
                        {"id": 123, "plan": {"name": "One", "type": "shadowsocks"}},
                        {"id": 124, "plan": {"name": "Two", "type": "shadowsocks"}},
                    ],
                )
            return httpx.Response(
                200,
                json=[
                    {
                        "hostname": "node.example.invalid",
                        "port": 443,
                        "encryption": "chacha20-ietf-poly1305",
                        "password": "test-node-secret",
                        "alias": "Example",
                        "enable": 1,
                    }
                ],
            )

        with httpx.Client(transport=httpx.MockTransport(handle)) as http:
            nodes = MonoCloudClient(MonoCloudSettings(), http).fetch_all_nodes(
                "test-token"
            )
        self.assertEqual([node.plan_id for node in nodes], ["123", "124"])
        self.assertEqual(
            paths, ["/api/service", "/api/shadowsocks/123", "/api/shadowsocks/124"]
        )
