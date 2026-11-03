import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urljoin, urlsplit

import httpx
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from monocloud_subscription.config import load_config
from monocloud_subscription.monocloud import MonoCloudSettings
from monocloud_subscription.tokens import TokenStore
from monocloud_subscription.web import create_app


class LoginPageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "config.toml"
        path.write_text(
            'data_dir = "data"\n[monocloud]\nclient_id = "fake-client"\nclient_secret = "fake-client-secret"\n',
            encoding="utf-8",
        )
        self.config = load_config(path)
        self.requests = []

    def client(
        self, status=200, payload=None, admin_password=None, base_url="http://localhost"
    ):
        if payload is None:
            payload = {"access_token": "fake-access-token"}

        def handle(request):
            self.requests.append(request)
            return httpx.Response(status, json=payload)

        app = create_app(
            self.config,
            admin_password=admin_password,
            transport=httpx.MockTransport(handle),
        )
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url
        )
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_page_and_packaged_assets_are_available_without_secrets(self):
        client = self.client()
        page = await client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('name="password"', page.text)
        self.assertNotIn("fake-client-secret", page.text)
        self.assertEqual((await client.get("/assets/login.css")).status_code, 200)
        self.assertEqual((await client.get("/assets/login.js")).status_code, 200)
        self.assertEqual(page.headers["cache-control"], "no-store")

    async def test_page_assets_resolve_inside_reverse_proxy_mount(self):
        class Assets(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []

            def handle_starttag(self, tag, attributes):
                attributes = dict(attributes)
                if tag == "script":
                    self.urls.append(attributes["src"])
                elif tag == "link":
                    self.urls.append(attributes["href"])

        client = self.client()
        assets = Assets()
        assets.feed((await client.get("/")).text)
        for url in assets.urls:
            external = urlsplit(urljoin("https://example.invalid/mono/", url)).path
            self.assertTrue(external.startswith("/mono/"), external)
            # A strip-prefix reverse proxy forwards this path to the application.
            self.assertEqual(
                (await client.get(external.removeprefix("/mono"))).status_code, 200
            )

    async def test_login_saves_only_token_and_returns_no_secrets(self):
        response = await self.client().post(
            "/api/login",
            json={"email": "user@example.invalid", "password": "fake-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token_saved"])
        self.assertEqual(TokenStore(self.config.token_file).load(), "fake-access-token")
        for secret in ("fake-password", "fake-access-token", "fake-client-secret"):
            self.assertNotIn(secret, response.text)
        self.assertNotIn("fake-password", self.config.token_file.read_text())
        self.assertEqual(len(self.requests), 1)

    async def test_rejected_login_preserves_existing_token(self):
        TokenStore(self.config.token_file).save("fake-old-token")
        response = await self.client(
            401, {"message": "fake-upstream-private-value"}
        ).post(
            "/api/login",
            json={"email": "user@example.invalid", "password": "fake-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(TokenStore(self.config.token_file).load(), "fake-old-token")
        self.assertNotIn("fake-upstream-private-value", response.text)

    async def test_validation_errors_never_echo_input(self):
        client = self.client()
        for payload in (
            {"password": "fake-private-input"},
            {
                "email": "user@example.invalid",
                "password": {"secret": "fake-private-input"},
            },
        ):
            with self.subTest(payload=payload):
                response = await client.post("/api/login", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("fake-private-input", response.text)
        self.assertEqual(self.requests, [])

    async def test_status_reports_saved_token_without_claiming_remote_validity(self):
        client = self.client()
        self.assertEqual(
            (await client.get("/api/status")).json(),
            {"oauth_configured": True, "token_saved": False},
        )
        TokenStore(self.config.token_file).save("fake-existing-token")
        response = await client.get("/api/status")
        self.assertTrue(response.json()["token_saved"])
        self.assertNotIn("fake-existing-token", response.text)
        self.assertEqual(self.requests, [])

    async def test_missing_oauth_settings_does_not_contact_upstream(self):
        self.config = replace(self.config, monocloud=MonoCloudSettings())
        client = self.client()
        self.assertFalse((await client.get("/api/status")).json()["oauth_configured"])
        response = await client.post(
            "/api/login",
            json={"email": "user@example.invalid", "password": "fake-password"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.requests, [])

    async def test_cross_origin_and_non_json_login_are_rejected(self):
        client = self.client()
        payload = {"email": "user@example.invalid", "password": "fake-password"}
        self.assertEqual(
            (
                await client.post(
                    "/api/login",
                    json=payload,
                    headers={"Origin": "https://other.invalid"},
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (await client.post("/api/login", data=payload)).status_code, 415
        )
        self.assertEqual(self.requests, [])

    async def test_management_password_protects_page_and_api(self):
        client = self.client(admin_password="fake-management-password")
        self.assertEqual((await client.get("/")).status_code, 401)
        self.assertEqual((await client.get("/api/status")).status_code, 401)
        self.assertEqual(
            (await client.get("/api/status", auth=("admin", "wrong"))).status_code, 401
        )
        self.assertEqual(
            (
                await client.get(
                    "/api/status", auth=("admin", "fake-management-password")
                )
            ).status_code,
            200,
        )

    async def test_unprotected_app_rejects_non_loopback_host(self):
        response = await self.client().get(
            "/api/status", headers={"Host": "other.invalid"}
        )
        self.assertEqual(response.status_code, 403)

    async def test_origin_without_host_returns_json_error(self):
        client = self.client()
        request = client.build_request(
            "POST",
            "/api/login",
            json={"email": "user@example.invalid", "password": "fake-password"},
            headers={"Origin": "http://localhost"},
        )
        del request.headers["host"]
        response = await client.send(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_host")
        self.assertEqual(self.requests, [])

    async def test_same_origin_accepts_explicit_default_ports(self):
        for base, host, origin in (
            ("http://localhost", "localhost:80", "http://localhost"),
            ("https://localhost", "localhost:443", "https://localhost"),
            ("http://localhost", "[::1]:80", "http://[::1]"),
        ):
            with self.subTest(base=base, host=host):
                response = await self.client(base_url=base).post(
                    "/api/login",
                    json={"email": "user@example.invalid", "password": "fake-password"},
                    headers={"Host": host, "Origin": origin},
                )
                self.assertEqual(response.status_code, 200)

    async def test_origin_still_rejects_different_schemes_ports_and_invalid_ports(self):
        client = self.client()
        for origin in (
            "https://localhost",
            "http://localhost:8081",
            "http://localhost:invalid",
        ):
            with self.subTest(origin=origin):
                response = await client.post(
                    "/api/login",
                    json={"email": "user@example.invalid", "password": "fake-password"},
                    headers={"Origin": origin},
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.requests, [])

    async def test_tls_proxy_origin_requires_an_explicitly_trusted_proxy(self):
        app = create_app(
            self.config,
            admin_password="fake-management-password",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"access_token": "fake-token"})
            ),
        )
        proxy_app = ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"])
        for address, expected in (("127.0.0.1", 200), ("127.0.0.2", 403)):
            with self.subTest(proxy=address):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=proxy_app, client=(address, 123)),
                    base_url="http://service.example.invalid",
                ) as client:
                    response = await client.post(
                        "/api/login",
                        auth=("admin", "fake-management-password"),
                        json={
                            "email": "user@example.invalid",
                            "password": "fake-password",
                        },
                        headers={
                            "X-Forwarded-Proto": "https",
                            "Origin": "https://service.example.invalid",
                        },
                    )
                self.assertEqual(response.status_code, expected)

    async def test_rejected_requests_have_security_headers(self):
        client = self.client()
        responses = [
            await client.post(
                "/api/login", json={}, headers={"Origin": "https://other.invalid"}
            ),
            await client.post("/api/login", data={}),
            await self.client(admin_password="fake-management-password").get("/"),
        ]
        self.assertEqual([r.status_code for r in responses], [403, 415, 401])
        for response in responses:
            self.assertEqual(response.headers.get("cache-control"), "no-store")
            self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
            self.assertIn(
                "frame-ancestors 'none'",
                response.headers.get("content-security-policy", ""),
            )

    async def test_oauth_client_errors_are_configuration_failures(self):
        for status, code in (
            (400, "invalid_client"),
            (401, "invalid_client"),
            (400, "invalid_request"),
        ):
            with self.subTest(status=status, code=code):
                TokenStore(self.config.token_file).save("fake-old-token")
                response = await self.client(
                    status, {"error": code, "message": "fake-private-message"}
                ).post(
                    "/api/login",
                    json={"email": "user@example.invalid", "password": "fake-password"},
                )
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["code"], "oauth_client_rejected")
                self.assertNotIn("fake-private-message", response.text)
                self.assertEqual(
                    TokenStore(self.config.token_file).load(), "fake-old-token"
                )

    async def test_upstream_failure_is_sanitized_and_preserves_token(self):
        TokenStore(self.config.token_file).save("fake-old-token")
        response = await self.client(500, {"message": "fake-private-upstream"}).post(
            "/api/login",
            json={"email": "user@example.invalid", "password": "fake-password"},
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "upstream_unavailable")
        self.assertNotIn("fake-private-upstream", response.text)
        self.assertEqual(TokenStore(self.config.token_file).load(), "fake-old-token")

    async def test_storage_failure_is_sanitized_and_preserves_token(self):
        TokenStore(self.config.token_file).save("fake-old-token")
        with patch(
            "monocloud_subscription.web.TokenStore.save",
            side_effect=ValueError("fake-private-storage"),
        ):
            response = await self.client().post(
                "/api/login",
                json={"email": "user@example.invalid", "password": "fake-password"},
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "token_save_failed")
        self.assertNotIn("fake-private-storage", response.text)
        self.assertEqual(TokenStore(self.config.token_file).load(), "fake-old-token")


class SubscriptionWebTests(unittest.IsolatedAsyncioTestCase):
    setUp = LoginPageTests.setUp
    client = LoginPageTests.client

    async def details(self, client):
        response = await client.get("/api/subscription")
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_native_download_uses_url_key_without_basic_auth(self):
        client = self.client(
            admin_password="constructed-admin", base_url="http://example.invalid"
        )
        client.auth = ("admin", "constructed-admin")
        details = await self.details(client)
        self.assertFalse(details["tailscale_enabled"])
        path = httpx.URL(details["url"]).raw_path.decode()
        client.auth = None
        with patch(
            "monocloud_subscription.web.generate_subscription",
            return_value="mode: rule\nrules: [MATCH,DIRECT]\n",
        ) as generate:
            response = await client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("mode: rule", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertIn("yaml", response.headers["content-type"])
            head = await client.head(path)
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head.content, b"")
            self.assertEqual(generate.call_count, 2)
            for wrong in (
                "/subscriptions/wrong/clash.yaml",
                path.replace("clash.yaml", "surge.conf"),
                "/subscriptions",
            ):
                self.assertEqual((await client.get(wrong)).status_code, 404)
            self.assertEqual(generate.call_count, 2)
        self.assertEqual((await client.get("/api/subscription")).status_code, 401)
        self.assertEqual((await client.get("/")).status_code, 401)

    async def test_url_and_toggle_persist_and_preserve_private_tailscale_settings(self):
        from monocloud_subscription.clash import TailscaleSettings

        self.config = replace(
            self.config, tailscale=TailscaleSettings(auth_key="constructed-ts-key")
        )
        client = self.client()
        before = await self.details(client)
        response = await client.post(
            "/api/subscription",
            json={"tailscale_enabled": True},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(response.status_code, 200)
        after = await self.details(self.client())
        self.assertTrue(after["tailscale_enabled"])
        self.assertEqual(before["url"], after["url"])
        self.assertNotIn("constructed-ts-key", str(after))
        with patch(
            "monocloud_subscription.web.generate_subscription",
            return_value="mode: rule",
        ) as generate:
            await client.get(httpx.URL(after["url"]).raw_path.decode())
            effective = generate.call_args.args[0]
            self.assertTrue(effective.tailscale.enabled)
            self.assertEqual(effective.tailscale.auth_key, "constructed-ts-key")
        await client.post("/api/subscription", json={"tailscale_enabled": False})
        self.assertFalse((await self.details(client))["tailscale_enabled"])

    async def test_settings_require_same_origin_json_and_strict_boolean(self):
        client = self.client()
        for kwargs, status in (
            (
                {
                    "json": {"tailscale_enabled": True},
                    "headers": {"Origin": "https://evil.invalid"},
                },
                403,
            ),
            (
                {
                    "content": "private-secret",
                    "headers": {"Content-Type": "text/plain"},
                },
                415,
            ),
            ({"json": {"tailscale_enabled": "private-secret"}}, 422),
            ({"json": {"tailscale_enabled": True, "auth_key": "private-secret"}}, 422),
        ):
            response = await client.post("/api/subscription", **kwargs)
            self.assertEqual(response.status_code, status)
            self.assertNotIn("private-secret", response.text)
        self.assertFalse((await self.details(client))["tailscale_enabled"])

    async def test_public_base_url_and_private_key_override(self):
        from monocloud_subscription.config import ServerSettings

        self.config = replace(
            self.config,
            server=ServerSettings(
                public_url="https://subscriptions.example.invalid/mono"
            ),
            subscription_key="constructed-key-01234567890123456789",
        )
        details = await self.details(self.client())
        self.assertEqual(
            details["url"],
            "https://subscriptions.example.invalid/mono/subscriptions/constructed-key-01234567890123456789/clash.yaml",
        )

    async def test_generation_failures_do_not_echo_secrets(self):
        from monocloud_subscription.monocloud import AuthenticationError

        client = self.client()
        path = httpx.URL((await self.details(client))["url"]).raw_path.decode()
        for exception, status, code in (
            (AuthenticationError("private-secret"), 401, "login_required"),
            (ValueError("private-secret"), 502, "generation_failed"),
        ):
            with patch(
                "monocloud_subscription.web.generate_subscription",
                side_effect=exception,
            ):
                response = await client.get(path)
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["code"], code)
            self.assertNotIn("private-secret", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_state_write_failure_preserves_toggle_and_link(self):
        client = self.client()
        before = await self.details(client)
        with patch(
            "monocloud_subscription.subscription_state.os.replace",
            side_effect=OSError("private-secret"),
        ):
            response = await client.post(
                "/api/subscription", json={"tailscale_enabled": True}
            )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-secret", response.text)
        self.assertEqual(await self.details(client), before)

    async def test_download_composes_real_generator_snapshot_and_all_nodes(self):
        import hashlib
        import json

        import yaml
        from test_clash import TEMPLATE

        root = self.config.data_dir.parent / "snapshot"
        root.mkdir()
        (root / "Clash_ss").write_bytes(TEMPLATE)
        (root / "update.json").write_text(
            json.dumps(
                {
                    "templates": [
                        {
                            "name": "Clash_ss",
                            "size": len(TEMPLATE),
                            "sha256": hashlib.sha256(TEMPLATE).hexdigest(),
                        }
                    ]
                }
            )
        )
        self.config = replace(self.config, template_dir=root)
        TokenStore(self.config.token_file).save("constructed-token")

        def upstream(request):
            self.assertEqual(
                request.headers["Authorization"], "Bearer constructed-token"
            )
            if request.url.path == "/api/service":
                return httpx.Response(
                    200,
                    json=[
                        {"id": 1, "plan": {"name": "Example", "type": "shadowsocks"}}
                    ],
                )
            return httpx.Response(
                200,
                json=[
                    {
                        "hostname": "node.example.invalid",
                        "port": 443,
                        "encryption": "aes-128-gcm",
                        "password": "constructed-node-password",
                        "alias": name,
                    }
                    for name in ("One", "Two")
                ],
            )

        app = create_app(self.config, transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            details = await self.details(client)
            response = await client.get(details["url"])
            self.assertEqual(response.status_code, 200)
            plain = yaml.safe_load(response.text)
            self.assertEqual(len(plain["proxies"]), 2)
            self.assertEqual(plain["proxies"][0]["server"], "node.example.invalid")
            self.assertNotIn("tailscale", response.text.lower())
            await client.post("/api/subscription", json={"tailscale_enabled": True})
            enabled = yaml.safe_load((await client.get(details["url"])).text)
            self.assertEqual(enabled["proxies"][-1]["type"], "tailscale")
            self.assertEqual(enabled["rules"][-len(plain["rules"]) :], plain["rules"])
            self.assertEqual((await self.details(client))["url"], details["url"])


class VerifiedAccountTests(unittest.IsolatedAsyncioTestCase):
    setUp = LoginPageTests.setUp
    client = LoginPageTests.client

    async def test_page_embeds_clash_mi_guide_with_optional_overlay(self):
        page = await self.client().get("/")
        self.assertIn('id="guide-clash-mi"', page.text)
        self.assertIn("基础接入", page.text)
        self.assertIn("可选：增加 Tailscale 能力", page.text)
        self.assertNotIn("<!-- CLIENT_GUIDES -->", page.text)
        self.assertNotIn('id="guide-surge"', page.text)
        self.assertNotIn('id="guide-sing-box"', page.text)

    async def test_signed_out_verified_status_does_not_contact_upstream(self):
        result = await self.client().get("/api/status?verify=true")
        self.assertEqual(result.json()["account_state"], "signed_out")
        self.assertEqual(result.json()["plan_count"], 0)
        self.assertEqual(self.requests, [])

    async def test_verified_saved_session_reports_service_count_without_account_data(
        self,
    ):
        TokenStore(self.config.token_file).save("constructed-token")
        result = await self.client(
            payload=[
                {"id": 1, "plan": {"name": "private-plan-name", "type": "shadowsocks"}},
                {"id": 2, "plan": {"name": "Other", "type": "shadowsocks"}},
            ]
        ).get("/api/status?verify=true")
        self.assertEqual(result.json()["account_state"], "connected")
        self.assertEqual(result.json()["plan_count"], 2)
        self.assertNotIn("private-plan-name", result.text)
        self.assertNotIn("constructed-token", result.text)
        self.assertEqual(self.requests[0].url.path, "/api/service")

    async def test_auth_rejection_expands_relogin_but_keeps_token(self):
        TokenStore(self.config.token_file).save("constructed-token")
        result = await self.client(status=401).get("/api/status?verify=true")
        self.assertEqual(result.json()["account_state"], "expired")
        self.assertTrue(result.json()["token_saved"])
        self.assertEqual(TokenStore(self.config.token_file).load(), "constructed-token")

    async def test_upstream_outage_is_not_reported_as_expired_credentials(self):
        TokenStore(self.config.token_file).save("constructed-token")
        result = await self.client(status=503).get("/api/status?verify=true")
        self.assertEqual(result.json()["account_state"], "unavailable")
        self.assertTrue(result.json()["token_saved"])
