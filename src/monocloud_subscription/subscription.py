"""Compose existing account discovery and the Clash generator for the web layer."""

import httpx

from monocloud_subscription.clash import generate_clash
from monocloud_subscription.config import Config
from monocloud_subscription.monocloud import (
    AuthenticationError,
    MonoCloudClient,
    Node,
    Plan,
)
from monocloud_subscription.templates import fetch_template, load_template_snapshot
from monocloud_subscription.tokens import TokenStore


def fetch_subscription_catalog(
    config: Config, http: httpx.Client
) -> tuple[list[Plan], list[Node]]:
    """Fetch the available plans and nodes from one saved session."""
    store = TokenStore(config.token_file)
    # One consistent account snapshot, including a possible rotating refresh.
    with store.locked():
        try:
            token = store.load()
        except ValueError:
            raise AuthenticationError(
                "Sign in through the web interface before downloading."
            ) from None
        client = MonoCloudClient(config.monocloud, http, token_store=store)
        plans = client.fetch_plans(token)
        nodes = client.fetch_all_nodes(token, [plan.service_id for plan in plans])
    return plans, nodes


def generate_subscription(config: Config, http: httpx.Client) -> str:
    """Return complete YAML or fail without writing partial configuration."""
    plans, nodes = fetch_subscription_catalog(config, http)
    template = (
        load_template_snapshot(config.template_dir)
        if config.template_dir
        else fetch_template(http, config.monocloud)
    )
    return generate_clash(template, nodes, config.clash, config.tailscale, plans=plans)
