"""Structured Clash/mihomo rendering; no network requests or file writes."""

from copy import deepcopy
from dataclasses import dataclass, field
from ipaddress import ip_network

import yaml

from monocloud_subscription.monocloud import Node
from monocloud_subscription.templates import validate_template


@dataclass(frozen=True)
class ClashSettings:
    mixed_port: int = 7890


@dataclass(frozen=True)
class TailscaleSettings:
    enabled: bool = False
    hostname: str = ""
    state_dir: str = "tailscale"
    auth_key: str = field(default="", repr=False)
    control_url: str = ""
    routes: tuple[str, ...] = ()


def generate_clash(
    template: dict,
    nodes: list[Node],
    clash: ClashSettings,
    tailscale: TailscaleSettings,
) -> str:
    """Build a complete subscription, preserving the official rule sequence."""
    result = deepcopy(validate_template(template))
    if not nodes:
        raise ValueError("No available Shadowsocks nodes for generation.")
    result["mixed-port"] = clash.mixed_port
    result["allow-lan"] = False
    used = {
        "Proxy",
        "Tailscale",
        "DIRECT",
        "REJECT",
        "REJECT-DROP",
        "PASS",
        "COMPATIBLE",
        "GLOBAL",
    }
    proxies = []
    for node in nodes:
        name = node.name
        number = 2
        while name in used:
            name = f"{node.name} ({number})"
            number += 1
        used.add(name)
        proxies.append(
            {
                "name": name,
                "type": "ss",
                "server": node.server,
                "port": node.port,
                "cipher": node.cipher,
                "password": node.password,
                "udp": True,
            }
        )
    result["proxy-groups"] = [
        {
            "name": "Proxy",
            "type": "select",
            "proxies": [proxy["name"] for proxy in proxies],
        }
    ]
    dns = result["dns"]
    # Preserve the official IP-based bootstrap policy, adding a default only
    # when absent. Validation rejects a hostname-dependent bootstrap chain.
    dns.setdefault("default-nameserver", ["223.5.5.5", "119.29.29.29"])
    # Official proxy-server DNS already uses IP-based resolvers, including
    # encrypted DNS. Preserve that policy rather than downgrading it to UDP.
    dns.setdefault("proxy-server-nameserver", ["223.5.5.5", "119.29.29.29"])
    if tailscale.enabled:
        # mihomo sends tsnet's interactive authorization URL to its info log.
        # The official template's error level would hide first-time login.
        if not tailscale.auth_key and result.get("log-level") in (
            "warning",
            "error",
            "silent",
        ):
            result["log-level"] = "info"
        ts = {
            "name": "Tailscale",
            "type": "tailscale",
            "state-dir": tailscale.state_dir,
            "ephemeral": False,
            "udp": True,
            "accept-routes": bool(tailscale.routes),
        }
        # Leave the underlying dialer direct: mihomo #3142 reports that routing
        # tsnet's wildcard UDP listener through a proxy fails before login.
        for key, value in (
            ("hostname", tailscale.hostname),
            ("auth-key", tailscale.auth_key),
            ("control-url", tailscale.control_url),
        ):
            if value:
                ts[key] = value
        proxies.append(ts)
        prefix = [
            "DOMAIN-SUFFIX,ts.net,Tailscale",
            "IP-CIDR,100.64.0.0/10,Tailscale,no-resolve",
            "IP-CIDR6,fd7a:115c:a1e0::/48,Tailscale,no-resolve",
        ]
        for route in tailscale.routes:
            network = ip_network(route, strict=True)
            kind = "IP-CIDR" if network.version == 4 else "IP-CIDR6"
            prefix.append(f"{kind},{network},Tailscale,no-resolve")
        result["rules"] = prefix + result["rules"]
        dns.setdefault("nameserver-policy", {})["+.ts.net"] = "ts://Tailscale"
        dns.setdefault("fake-ip-filter", []).append("+.ts.net")
    result["proxies"] = proxies
    return yaml.safe_dump(result, allow_unicode=True, sort_keys=False)
