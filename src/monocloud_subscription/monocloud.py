"""Confirmed MonoCloud login and Shadowsocks node API operations."""

from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from monocloud_subscription.tokens import valid_token


class MonoCloudError(ValueError):
    """An API failure safe to show without exposing remote response contents."""


class AuthenticationError(MonoCloudError):
    """Authentication requires user action rather than automatic login retries."""


@dataclass(frozen=True)
class MonoCloudSettings:
    base_url: str = "https://api.bluecloudworks.com"
    # Compatibility identity confirmed by read-only requests; both are configurable.
    user_agent: str = "MonocloudGO-1.0.1"
    client_version: str = "1.0.1"
    client_id: str = ""
    client_secret: str = field(default="", repr=False)


@dataclass(frozen=True)
class Plan:
    # The service record ID is the node endpoint's identifier, not plan.id.
    id: str
    name: str


@dataclass(frozen=True)
class Node:
    plan_id: str
    name: str
    server: str
    port: int
    cipher: str
    password: str = field(repr=False)


class MonoCloudClient:
    def __init__(self, settings: MonoCloudSettings, http: httpx.Client):
        self.settings = settings
        self.http = http

    def _request(self, method: str, path: str, *, token=None, data=None):
        headers = {"Accept": "application/json", "User-Agent": self.settings.user_agent}
        if self.settings.client_version:
            headers["X-Client-Version"] = self.settings.client_version
        if token is not None:
            if not valid_token(token):
                raise AuthenticationError("Invalid token. Run import-token or login.")
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self.http.request(
                method,
                f"{self.settings.base_url.rstrip('/')}{path}",
                headers=headers,
                data=data,
                timeout=20,
                follow_redirects=False,
            )
        except httpx.RequestError:
            raise MonoCloudError("MonoCloud network request failed.") from None
        if response.status_code in (401, 403) or (
            path == "/oauth/token" and response.status_code == 400
        ):
            raise AuthenticationError(
                "Authentication rejected. Run login or import-token with a valid token."
            )
        if not response.is_success:
            raise MonoCloudError(
                f"MonoCloud request failed (HTTP {response.status_code})."
            )
        try:
            return response.json()
        except ValueError:
            raise MonoCloudError("MonoCloud returned invalid JSON.") from None

    def login(self, username: str, password: str) -> str:
        if not self.settings.client_id or not self.settings.client_secret:
            raise MonoCloudError(
                "Configure monocloud.client_id and client_secret for login."
            )
        if not username.strip() or not password:
            raise MonoCloudError("Email and password are required for login.")
        values = self._request(
            "POST",
            "/oauth/token",
            data={
                "grant_type": "password",
                "username": username,
                "password": password,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
        )
        if not isinstance(values, dict) or not valid_token(values.get("access_token")):
            raise MonoCloudError("MonoCloud login response has no valid access token.")
        return values["access_token"]

    def fetch_plans(self, token: str) -> list[Plan]:
        values = self._request("GET", "/api/service", token=token)
        if not isinstance(values, list):
            raise MonoCloudError("Unexpected service response: expected a JSON array.")
        plans = []
        for value in values:
            if not isinstance(value, dict) or not isinstance(value.get("plan"), dict):
                raise MonoCloudError("Invalid service entry in MonoCloud response.")
            product = value["plan"]
            if not isinstance(product.get("type"), str):
                raise MonoCloudError("Service response is missing its plan type.")
            if product["type"] != "shadowsocks":
                continue
            service_id = value.get("id")
            if not (
                (type(service_id) is int and service_id > 0)
                or (isinstance(service_id, str) and service_id.strip())
            ):
                raise MonoCloudError("Service response has an invalid service ID.")
            name = product.get("name")
            if not isinstance(name, str) or not name.strip():
                name = "Shadowsocks plan"
            plans.append(Plan(str(service_id), name))
        return plans

    def fetch_all_nodes(
        self, token: str, plan_ids: list[str] | None = None
    ) -> list[Node]:
        if plan_ids is None:
            plan_ids = [plan.id for plan in self.fetch_plans(token)]
        nodes = []
        for plan_id in dict.fromkeys(plan_ids):
            nodes.extend(self.fetch_nodes(token, plan_id))
        return nodes

    def fetch_nodes(self, token: str, plan_id: str) -> list[Node]:
        if not plan_id.strip():
            raise MonoCloudError("A plan ID is required.")
        values = self._request(
            "GET", f"/api/shadowsocks/{quote(plan_id, safe='')}", token=token
        )
        if not isinstance(values, list):
            raise MonoCloudError("Unexpected node response: expected a JSON array.")
        nodes = []
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise MonoCloudError("Invalid node entry in MonoCloud response.")
            if value.get("enable", True) in (False, 0):
                continue
            if any(
                not isinstance(value.get(key), str) or not value[key].strip()
                for key in ("hostname", "encryption", "password")
            ):
                raise MonoCloudError(
                    "Node response is missing required connection fields."
                )
            port = value.get("port")
            if type(port) is not int or not 1 <= port <= 65535:
                raise MonoCloudError("Node response has an invalid port.")
            alias = value.get("alias")
            name = (
                alias if isinstance(alias, str) and alias.strip() else f"node-{index}"
            )
            nodes.append(
                Node(
                    plan_id,
                    name,
                    value["hostname"],
                    port,
                    value["encryption"],
                    value["password"],
                )
            )
        return nodes
