"""Private account management and credential-protected subscription downloads."""

import base64
import secrets
from dataclasses import replace
from importlib.resources import files
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool

from monocloud_subscription.config import Config
from monocloud_subscription.monocloud import (
    AuthenticationError,
    MonoCloudClient,
    MonoCloudError,
    OAuthConfigurationError,
)
from monocloud_subscription.subscription import generate_subscription
from monocloud_subscription.subscription_state import SubscriptionStore
from monocloud_subscription.tokens import TokenStore


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=4096)


class SubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tailscale_enabled: StrictBool


def normalized_origin(value: str) -> tuple[str, str, int] | None:
    try:
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
        ):
            return None
        port = (
            url.port if url.port is not None else (443 if url.scheme == "https" else 80)
        )
        return url.scheme, url.hostname, port
    except ValueError:
        return None


def create_app(
    config: Config,
    *,
    admin_password: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    resources = files("monocloud_subscription").joinpath("static")
    store = TokenStore(config.token_file)
    subscriptions = SubscriptionStore(config.data_dir / "subscription.json")
    subscriptions.load()  # Initialize once before concurrent requests can arrive.

    def secure(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    def error(
        code: str, status: int, headers: dict[str, str] | None = None
    ) -> Response:
        return secure(JSONResponse({"code": code}, status_code=status, headers=headers))

    @app.middleware("http")
    async def protect(request: Request, call_next):
        host = request.headers.get("host", "")
        expected = (
            normalized_origin(f"{request.scope['scheme']}://{host}") if host else None
        )
        if expected is None:
            return error("invalid_host", 400)
        is_download = (
            request.url.path == "/subscriptions"
            or request.url.path.startswith("/subscriptions/")
        )
        if not is_download:
            if admin_password:
                try:
                    scheme, encoded = request.headers.get("authorization", "").split(
                        " ", 1
                    )
                    if scheme.lower() != "basic":
                        raise ValueError
                    username, password = (
                        base64.b64decode(encoded, validate=True).decode().split(":", 1)
                    )
                    allowed = secrets.compare_digest(
                        username.encode(), b"admin"
                    ) and secrets.compare_digest(
                        password.encode(), admin_password.encode()
                    )
                except (ValueError, UnicodeDecodeError):
                    allowed = False
                if not allowed:
                    return error(
                        "management_auth_required",
                        401,
                        headers={
                            "WWW-Authenticate": 'Basic realm="Subscription management", charset="UTF-8"',
                        },
                    )
            elif expected[1] not in ("localhost", "127.0.0.1", "::1"):
                return error("local_access_only", 403)

        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin is not None and normalized_origin(origin) != expected:
                return error("cross_origin_rejected", 403)
            if (
                request.headers.get("content-type", "").split(";", 1)[0]
                != "application/json"
            ):
                return error("json_required", 415)

        return secure(await call_next(request))

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exception):
        # Framework defaults include input values, which can contain passwords.
        return error(
            "invalid_login_input"
            if request.url.path == "/api/login"
            else "invalid_input",
            422,
        )

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def index():
        page = resources.joinpath("login.html").read_text(encoding="utf-8")
        guide = resources.joinpath("guides", "clash-mi.html").read_text(
            encoding="utf-8"
        )
        return HTMLResponse(page.replace("<!-- CLIENT_GUIDES -->", guide))

    @app.get("/assets/{name}")
    def asset(name: str):
        types = {
            "login.css": "text/css",
            "login.js": "text/javascript",
            "favicon.svg": "image/svg+xml",
        }
        if name not in types:
            return error("not_found", 404)
        return Response(resources.joinpath(name).read_bytes(), media_type=types[name])

    @app.get("/api/status")
    def status(verify: bool = False):
        try:
            token = store.load()
        except ValueError:
            token = None
        result = {
            "oauth_configured": bool(
                config.monocloud.client_id and config.monocloud.client_secret
            ),
            "token_saved": token is not None,
        }
        if verify:
            state = "signed_out"
            names = []
            if token is not None:
                try:
                    with httpx.Client(transport=transport) as http:
                        plans = MonoCloudClient(config.monocloud, http).fetch_plans(
                            token
                        )
                    state = "connected"
                    names = [plan.name for plan in plans]
                except AuthenticationError:
                    state = "expired"
                except MonoCloudError:
                    state = "unavailable"
            result.update(account_state=state, plan_count=len(names), plan_names=names)
        return result

    @app.post("/api/login")
    def login(credentials: LoginRequest):
        if not config.monocloud.client_id or not config.monocloud.client_secret:
            return error("oauth_not_configured", 503)
        if not credentials.email.strip():
            return error("invalid_login_input", 422)
        try:
            with httpx.Client(transport=transport) as http:
                token = MonoCloudClient(config.monocloud, http).login(
                    credentials.email.strip(), credentials.password.get_secret_value()
                )
        except OAuthConfigurationError:
            return error("oauth_client_rejected", 503)
        except AuthenticationError:
            return error("login_rejected", 401)
        except MonoCloudError:
            return error("upstream_unavailable", 502)
        try:
            store.save(token)
        except ValueError:
            return error("token_save_failed", 500)
        return {"token_saved": True}

    def subscription_details(request: Request):
        state = subscriptions.load()
        key = config.subscription_key or state.key
        base = config.server.public_url or str(request.base_url).rstrip("/")
        return {
            "url": f"{base}/subscriptions/{key}/clash.yaml",
            "tailscale_enabled": (
                state.tailscale_enabled
                if state.tailscale_enabled is not None
                else config.tailscale.enabled
            ),
            # The page asks for an explicit first choice until one is saved.
            "tailscale_choice_saved": state.tailscale_enabled is not None,
        }

    @app.get("/api/subscription")
    def subscription_status(request: Request):
        try:
            return subscription_details(request)
        except ValueError:
            return error("subscription_state_unavailable", 500)

    @app.post("/api/subscription")
    def subscription_settings(settings: SubscriptionRequest, request: Request):
        try:
            subscriptions.set_enabled(settings.tailscale_enabled)
            return subscription_details(request)
        except ValueError:
            return error("subscription_state_save_failed", 500)

    @app.api_route("/subscriptions/{key}/clash.yaml", methods=["GET", "HEAD"])
    def download(key: str):
        try:
            state = subscriptions.load()
        except ValueError:
            return error("subscription_state_unavailable", 500)
        expected_key = config.subscription_key or state.key
        if not secrets.compare_digest(key.encode(), expected_key.encode()):
            return error("not_found", 404)
        enabled = (
            state.tailscale_enabled
            if state.tailscale_enabled is not None
            else config.tailscale.enabled
        )
        effective = replace(
            config, tailscale=replace(config.tailscale, enabled=enabled)
        )
        try:
            with httpx.Client(transport=transport) as http:
                content = generate_subscription(effective, http)
        except AuthenticationError:
            return error("login_required", 401)
        except ValueError:
            return error("generation_failed", 502)
        return Response(
            content,
            media_type="application/yaml",
            headers={"Content-Disposition": 'attachment; filename="clash.yaml"'},
        )

    return app
