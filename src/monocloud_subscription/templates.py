"""Download and verify MonoCloud's official Shadowsocks routing template."""

import hashlib
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
import yaml

from monocloud_subscription.monocloud import MonoCloudSettings

MANIFEST_URL = "https://static.monocloud.co/mono_go/update.json"


def validate_template(template: object) -> dict:
    if not isinstance(template, dict):
        raise ValueError("Unsupported MonoCloud template structure.")
    allowed = {
        "mixed-port",
        "allow-lan",
        "mode",
        "log-level",
        "dns",
        "proxies",
        "proxy-groups",
        "rules",
    }
    if template.keys() - allowed or template.get("mode", "rule") not in (
        "rule",
        "Rule",
    ):
        raise ValueError("Unsupported MonoCloud template options or mode.")
    groups = template.get("proxy-groups")
    rules = template.get("rules")
    if (
        not isinstance(template.get("dns"), dict)
        or not isinstance(groups, list)
        or len(groups) != 1
        or not isinstance(groups[0], dict)
        or groups[0].get("name") != "Proxy"
        or groups[0].get("type") != "select"
        or not isinstance(rules, list)
        or not rules
        or rules[-1] != "MATCH,Proxy"
    ):
        raise ValueError("Unsupported MonoCloud template structure.")
    dns = template["dns"]
    if "nameserver-policy" in dns and not isinstance(dns["nameserver-policy"], dict):
        raise ValueError("Invalid MonoCloud template DNS policy.")
    if "fake-ip-filter" in dns and (
        not isinstance(dns["fake-ip-filter"], list)
        or any(not isinstance(item, str) for item in dns["fake-ip-filter"])
    ):
        raise ValueError("Invalid MonoCloud template fake-IP filter.")
    if "default-nameserver" in dns:
        resolvers = dns["default-nameserver"]
        try:
            if not isinstance(resolvers, list) or not resolvers:
                raise ValueError
            for resolver in resolvers:
                if not isinstance(resolver, str):
                    raise ValueError
                host = urlsplit(resolver).hostname if "://" in resolver else resolver
                ip_address(host)
        except ValueError:
            raise ValueError(
                "Template bootstrap DNS must use IP-based resolvers."
            ) from None
    for rule in rules:
        if not isinstance(rule, str):
            raise ValueError("Invalid MonoCloud template rule.")
        parts = rule.split(",")
        if len(parts) < 2:
            raise ValueError("Invalid MonoCloud template rule.")
        target = parts[-2] if parts[-1] == "no-resolve" else parts[-1]
        # The current official template contains two DOMAIN rules ending in
        # DIRECT,DIRECT; mihomo accepts the extra parameter. Preserve them.
        if target not in {"Proxy", "DIRECT", "REJECT"}:
            raise ValueError("Unsupported MonoCloud template rule target.")
    return template


def fetch_template(http: httpx.Client, settings: MonoCloudSettings) -> dict:
    """Verify the exact resource bytes before normalizing known placeholders."""
    headers = {"User-Agent": settings.user_agent}
    try:
        response = http.get(
            MANIFEST_URL, headers=headers, timeout=20, follow_redirects=False
        )
        response.raise_for_status()
        manifest = response.json()
        entries = manifest["templates"]
        entry = next(item for item in entries if item["name"] == "Clash_ss")
        if not isinstance(entry["url"], str):
            raise ValueError
        url = urlsplit(entry["url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError
        asset = http.get(
            entry["url"], headers=headers, timeout=20, follow_redirects=False
        )
        asset.raise_for_status()
        if (
            len(asset.content) != entry["size"]
            or hashlib.sha256(asset.content).hexdigest() != entry["sha256"]
        ):
            raise ValueError("MonoCloud template size or SHA-256 verification failed.")
    except (httpx.HTTPError, KeyError, TypeError, StopIteration, ValueError):
        raise ValueError(
            "Cannot fetch or verify the official MonoCloud template."
        ) from None

    try:
        text = asset.content.decode("utf-8")
        for placeholder, value in (
            ("monoCloud_localport", "7890"),
            ("monoCloud_hostname", "example.invalid"),
            ("monoCloud_port", "443"),
            ("monoCloud_cipher", "aes-128-gcm"),
            ("monoCloud_password", "placeholder"),
            ("{tunnel}", ""),
            ("{Clash-rule}", ""),
        ):
            if placeholder not in text:
                raise ValueError
            text = text.replace(placeholder, value)
        template = yaml.safe_load(text)
    except (UnicodeDecodeError, yaml.YAMLError, ValueError):
        raise ValueError("Cannot parse the official MonoCloud template.") from None
    return validate_template(template)
