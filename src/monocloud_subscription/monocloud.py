"""Confirmed MonoCloud login and Shadowsocks node API operations."""

import math
import re
import time
from dataclasses import dataclass, field
from ipaddress import ip_address
from urllib.parse import quote

import httpx

from monocloud_subscription.server_list import ServerListCipher, decode_base64
from monocloud_subscription.tokens import Session, TokenStore, valid_token

SIGN_OUT_REASONS = {
    "signed_out_from_device",
    "signed_out_from_website",
    "sign_in_limit",
}
_HOST_LABEL = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?")


def _normalize_node_host(value: object) -> str | None:
    if not isinstance(value, str) or "%" in value:
        return None
    try:
        ip_address(value)
    except ValueError:
        try:
            hostname = value.encode("idna").decode("ascii")
        except UnicodeError:
            return None
        domain = hostname.removesuffix(".")
        if len(domain) > 253 or not all(
            _HOST_LABEL.fullmatch(label) for label in domain.split(".")
        ):
            return None
        return hostname
    return value


class MonoCloudError(ValueError):
    """An API failure safe to show without exposing remote response contents."""


class AuthenticationError(MonoCloudError):
    """Authentication requires user action rather than automatic login retries."""

    def __init__(self, message: str, *, status: int | None = None, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


class OAuthConfigurationError(MonoCloudError):
    """The server rejected application parameters rather than user credentials."""


@dataclass(frozen=True)
class MonoCloudSettings:
    base_url: str = "https://api.bluecloudworks.com"
    # Compatibility identity confirmed by read-only requests; both are configurable.
    user_agent: str = "MonocloudGO-1.5.0"
    client_version: str = "1.5.0"
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    api_version: str = "v2"
    response_key_id: str = ""
    response_key: str = field(default="", repr=False)
    request_context: str = field(default="", repr=False)
    client_platform: str = ""
    os_version: str = ""
    device_model: str = ""
    device_model_name: str = ""


@dataclass(frozen=True)
class Plan:
    service_id: str
    name: str


@dataclass(frozen=True)
class Node:
    service_id: str
    name: str
    server: str
    port: int
    cipher: str
    password: str = field(repr=False)


class MonoCloudClient:
    def __init__(
        self,
        settings: MonoCloudSettings,
        http: httpx.Client,
        *,
        token_store: TokenStore | None = None,
    ):
        if settings.api_version not in ("v2", "legacy"):
            raise MonoCloudError("Unsupported MonoCloud API version.")
        if bool(settings.response_key_id) != bool(settings.response_key):
            raise MonoCloudError("Configure both server-list response key settings.")
        self.settings = settings
        self.http = http
        self.token_store = token_store

    def _request(
        self, method: str, path: str, *, token=None, data=None, extra_headers=None
    ):
        if (
            token is None
            or self.token_store is None
            or self.settings.api_version == "legacy"
        ):
            return self._send(
                method, path, token=token, data=data, extra_headers=extra_headers
            )
        with self.token_store.locked():
            refreshed = False
            try:
                session = self.token_store.load_session()
            except ValueError:
                raise AuthenticationError(
                    "Invalid token. Sign in through the web interface."
                ) from None
            if (
                session.expires_at is not None
                and session.expires_at <= time.time() + 30
            ):
                if session.refresh_token:
                    session = self._rotate(session)
                    refreshed = True
                elif session.expires_at <= time.time():
                    self._end_session()
                    raise AuthenticationError(
                        "Token expired. Sign in through the web interface."
                    )
            try:
                return self._send(
                    method,
                    path,
                    token=session.access_token,
                    data=data,
                    extra_headers=extra_headers,
                )
            except AuthenticationError as exc:
                if exc.code in SIGN_OUT_REASONS or (
                    exc.status == 401 and (refreshed or not session.refresh_token)
                ):
                    self._end_session()
                if (
                    refreshed
                    or exc.status != 401
                    or not session.refresh_token
                    or exc.code
                    not in ("", "token_expired", "invalid_token", "unauthenticated")
                ):
                    raise
                session = self._rotate(session)
                try:
                    return self._send(
                        method,
                        path,
                        token=session.access_token,
                        data=data,
                        extra_headers=extra_headers,
                    )
                except AuthenticationError as retry_error:
                    if (
                        retry_error.status == 401
                        or retry_error.code in SIGN_OUT_REASONS
                    ):
                        self._end_session()
                    raise

    def _end_session(self) -> None:
        try:
            self.token_store.invalidate()
        except ValueError:
            raise MonoCloudError(
                "Cannot save account sign-out state. Sign in again through the web interface."
            ) from None

    def _rotate(self, session: Session) -> Session:
        try:
            refreshed = self.refresh_session(session)
        except AuthenticationError:
            self._end_session()
            raise
        try:
            self.token_store.save_session(refreshed)
        except ValueError:
            raise MonoCloudError(
                "Cannot save refreshed account session. Sign in again through the web interface."
            ) from None
        return refreshed

    def _send(
        self, method: str, path: str, *, token=None, data=None, extra_headers=None
    ):
        headers = {"Accept": "application/json", "User-Agent": self.settings.user_agent}
        if self.settings.client_version:
            headers["X-Client-Version"] = self.settings.client_version
        for name, value in (
            ("X-Client-Platform", self.settings.client_platform),
            ("X-OS-Version", self.settings.os_version),
            ("X-Device-Model", self.settings.device_model),
            ("X-Device-Model-Name", self.settings.device_model_name),
        ):
            if value:
                headers[name] = value
        headers.update(extra_headers or {})
        if token is not None:
            if not valid_token(token):
                raise AuthenticationError(
                    "Invalid token. Sign in through the web interface."
                )
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
        if path == "/oauth/token" and response.status_code in (400, 401):
            try:
                body = response.json()
                oauth_error = body.get("error") if isinstance(body, dict) else None
            except ValueError:
                oauth_error = None
            if oauth_error in (
                "invalid_client",
                "invalid_request",
                "unsupported_grant_type",
            ):
                raise OAuthConfigurationError(
                    "MonoCloud rejected the OAuth application configuration."
                )
            if oauth_error == "invalid_grant":
                raise AuthenticationError(
                    "Authentication rejected. Sign in again through the web interface."
                )
        if response.status_code in (401, 403):
            try:
                body = response.json()
                code = body.get("error", "") if isinstance(body, dict) else ""
                if (
                    isinstance(body, dict)
                    and isinstance(body.get("reason"), str)
                    and body["reason"] in SIGN_OUT_REASONS
                ):
                    code = body["reason"]
                if not isinstance(code, str):
                    code = ""
            except ValueError:
                code = ""
            raise AuthenticationError(
                "Authentication rejected. Sign in again through the web interface.",
                status=response.status_code,
                code=code,
            )
        if response.status_code == 426:
            raise MonoCloudError("MonoCloud requires a newer client protocol.")
        if not response.is_success:
            raise MonoCloudError(
                f"MonoCloud request failed (HTTP {response.status_code})."
            )
        try:
            if len(response.content) > 16 * 1024 * 1024:
                raise ValueError
            return response.json()
        except ValueError:
            raise MonoCloudError("MonoCloud returned invalid JSON.") from None

    def login(self, username: str, password: str) -> str:
        """Compatibility helper; browser login uses login_session to retain refresh state."""
        return self.login_session(username, password).access_token

    def login_session(self, username: str, password: str) -> Session:
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
        return self._parse_session(values)

    def refresh_session(self, session: Session) -> Session:
        if not session.refresh_token:
            raise AuthenticationError("Sign in again through the web interface.")
        if not self.settings.client_id or not self.settings.client_secret:
            raise OAuthConfigurationError(
                "Configure OAuth client credentials to refresh the session."
            )
        values = self._send(
            "POST",
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": session.refresh_token,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
        )
        return self._parse_session(values, previous_refresh=session.refresh_token)

    @staticmethod
    def _parse_session(values, *, previous_refresh=None) -> Session:
        if not isinstance(values, dict) or not valid_token(values.get("access_token")):
            raise MonoCloudError("MonoCloud login response has no valid access token.")
        refresh = values.get("refresh_token", previous_refresh)
        if refresh is not None and not valid_token(refresh):
            raise MonoCloudError("MonoCloud returned an invalid account session.")
        duration = values.get("expires_in")
        expiry = None
        if duration is not None:
            if isinstance(duration, str) and duration.isascii() and duration.isdigit():
                duration = int(duration)
            try:
                valid_duration = (
                    type(duration) in (int, float)
                    and math.isfinite(duration)
                    and duration > 0
                )
            except OverflowError:
                valid_duration = False
            if not valid_duration:
                raise MonoCloudError("MonoCloud returned an invalid token expiry.")
            expiry = time.time() + duration
        return Session(values["access_token"], refresh, expiry)

    def fetch_plans(self, token: str) -> list[Plan]:
        if self.settings.api_version == "v2":
            return self._fetch_v2_plans(token)
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
        self, token: str, service_ids: list[str] | None = None
    ) -> list[Node]:
        if service_ids is None:
            service_ids = [plan.service_id for plan in self.fetch_plans(token)]
        if self.settings.api_version == "v2":
            return self._fetch_v2_nodes(token, service_ids)
        nodes = []
        for service_id in dict.fromkeys(service_ids):
            nodes.extend(self.fetch_nodes(token, service_id))
        return nodes

    def fetch_nodes(self, token: str, service_id: str) -> list[Node]:
        if not service_id.strip():
            raise MonoCloudError("A service ID is required.")
        if self.settings.api_version == "v2":
            return self._fetch_v2_nodes(token, [service_id])
        values = self._request(
            "GET", f"/api/shadowsocks/{quote(service_id, safe='')}", token=token
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
                    service_id,
                    name,
                    value["hostname"],
                    port,
                    value["encryption"],
                    value["password"],
                )
            )
        return nodes

    @staticmethod
    def _service_id(value) -> str:
        if type(value) is int and value > 0:
            return str(value)
        if (
            isinstance(value, str)
            and value.isascii()
            and value.isdigit()
            and int(value) > 0
        ):
            return str(int(value))
        raise MonoCloudError("MonoCloud returned an invalid service ID.")

    def _fetch_v2_plans(self, token: str) -> list[Plan]:
        body = self._request("GET", "/api/v2/services", token=token)
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise MonoCloudError("Unexpected MonoCloud v2 services response.")
        plans = []
        seen = set()
        for item in body["data"]:
            if not isinstance(item, dict) or type(item.get("connectable")) is not bool:
                raise MonoCloudError("Invalid MonoCloud v2 service entry.")
            service_id = self._service_id(item.get("id"))
            if service_id in seen:
                raise MonoCloudError("Duplicate MonoCloud service ID.")
            seen.add(service_id)
            if not item["connectable"]:
                continue
            plan = item.get("plan")
            if not isinstance(plan, dict):
                raise MonoCloudError("Invalid MonoCloud v2 plan.")
            name = plan.get("name")
            if not isinstance(name, str) or not name.strip():
                raise MonoCloudError("Invalid MonoCloud v2 plan name.")
            plans.append(Plan(service_id, name))
        return plans

    def _fetch_v2_nodes(self, token: str, service_ids: list[str]) -> list[Node]:
        wanted = {self._service_id(i) for i in service_ids}
        if not wanted:
            return []
        cipher = None
        headers = {}
        if self.settings.response_key:
            try:
                cipher = ServerListCipher(
                    self.settings.response_key_id, self.settings.response_key
                )
                headers.update(cipher.request_headers())
            except ValueError:
                raise MonoCloudError(
                    "Invalid private server-list key settings."
                ) from None
        if self.settings.request_context:
            headers["X-Request-Context"] = self.settings.request_context
        body = self._request(
            "GET", "/api/v2/servers", token=token, extra_headers=headers
        )
        if not isinstance(body, dict) or "data" not in body:
            raise MonoCloudError("Unexpected MonoCloud v2 servers response.")
        groups = body["data"]
        if cipher is not None:
            try:
                groups = cipher.decode(groups)
            except ValueError:
                raise MonoCloudError(
                    "Cannot authenticate or decode the MonoCloud server list."
                ) from None
        elif not isinstance(groups, list):
            raise MonoCloudError(
                "Encrypted server list requires private response key settings."
            )
        nodes = []
        seen = set()
        for group in groups:
            if not isinstance(group, dict) or not isinstance(
                group.get("servers"), list
            ):
                raise MonoCloudError("Invalid MonoCloud v2 server group.")
            service_id = self._service_id(group.get("service_id"))
            if service_id in seen:
                raise MonoCloudError("Duplicate MonoCloud server group.")
            seen.add(service_id)
            if service_id not in wanted:
                continue
            for index, server in enumerate(group["servers"], start=1):
                node = self._v2_node(server, service_id, index)
                if node is not None:
                    nodes.append(node)
        return nodes

    @staticmethod
    def _v2_node(value, service_id: str, index: int) -> Node | None:
        if not isinstance(value, dict):
            raise MonoCloudError("Invalid MonoCloud v2 node.")
        protocol = value.get("protocol")
        if not isinstance(protocol, str) or not protocol.strip():
            raise MonoCloudError("Invalid MonoCloud v2 node protocol.")
        if protocol != "shadowsocks":
            return None
        params, auth = value.get("params"), value.get("auth")
        if not isinstance(params, dict) or not isinstance(auth, dict):
            raise MonoCloudError("Invalid MonoCloud v2 node parameters.")
        if params.keys() - {"method"} or auth.keys() - {
            "password",
            "username",
            "server_key",
            "user_key",
        }:
            raise MonoCloudError("Unsupported MonoCloud node parameters.")
        method, password, host, port = (
            params.get("method"),
            auth.get("password"),
            _normalize_node_host(value.get("host")),
            value.get("port"),
        )
        supported = {
            "aes-128-gcm",
            "aes-192-gcm",
            "aes-256-gcm",
            "chacha20-ietf-poly1305",
            "xchacha20-ietf-poly1305",
            "2022-blake3-aes-128-gcm",
            "2022-blake3-aes-256-gcm",
            "2022-blake3-chacha20-poly1305",
            "aes-128-cfb",
            "aes-192-cfb",
            "aes-256-cfb",
            "aes-128-ctr",
            "aes-192-ctr",
            "aes-256-ctr",
            "rc4-md5",
            "chacha20-ietf",
        }
        if not isinstance(method, str) or method not in supported:
            raise MonoCloudError("Unsupported MonoCloud Shadowsocks cipher.")
        if any(
            auth.get(k) not in (None, "")
            for k in ("username", "server_key", "user_key")
        ):
            raise MonoCloudError("Unsupported MonoCloud node authentication options.")
        if (
            type(port) is not int
            or not 1 <= port <= 65535
            or host is None
            or not isinstance(password, str)
            or not password.strip()
        ):
            raise MonoCloudError("Invalid MonoCloud node connection fields.")
        if method.startswith("2022-"):
            size = 16 if method == "2022-blake3-aes-128-gcm" else 32
            try:
                decode_base64(password, size)
            except ValueError:
                raise MonoCloudError(
                    "Invalid or unsupported Shadowsocks 2022 key."
                ) from None
        udp_port = value.get("udp_port")
        if (
            udp_port is not None
            and (type(udp_port) is not int or udp_port not in (0, port))
        ) or value.get("udp_port_range") is not None:
            raise MonoCloudError("Unsupported MonoCloud UDP port options.")
        alias = value.get("alias")
        name = alias if isinstance(alias, str) and alias.strip() else f"node-{index}"
        return Node(service_id, name, host, port, method, password)
