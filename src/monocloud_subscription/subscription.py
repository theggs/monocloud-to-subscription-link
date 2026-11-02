"""Compose existing account discovery and the Clash generator for the web layer."""

import httpx

from monocloud_subscription.clash import generate_clash
from monocloud_subscription.config import Config
from monocloud_subscription.monocloud import MonoCloudClient
from monocloud_subscription.templates import fetch_template
from monocloud_subscription.tokens import TokenStore


def generate_subscription(config: Config, http: httpx.Client) -> str:
    """Return complete YAML or fail without writing partial configuration."""
    token = TokenStore(config.token_file).load()
    nodes = MonoCloudClient(config.monocloud, http).fetch_all_nodes(token)
    template = fetch_template(http, config.monocloud)
    return generate_clash(template, nodes, config.clash, config.tailscale)
