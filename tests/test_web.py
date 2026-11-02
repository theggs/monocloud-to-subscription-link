import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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
