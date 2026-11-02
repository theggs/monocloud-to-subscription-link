import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import httpx

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

    def client(self, status=200, payload=None, admin_password=None):
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
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
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
