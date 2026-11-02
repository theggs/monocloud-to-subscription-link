import copy
import hashlib
import unittest

import httpx
import yaml

from monocloud_subscription.clash import (
    ClashSettings,
    TailscaleSettings,
    generate_clash,
)
from monocloud_subscription.monocloud import MonoCloudSettings, Node
from monocloud_subscription.templates import fetch_template

TEMPLATE = b"""mixed-port: monoCloud_localport
allow-lan: true
mode: Rule
dns:
  enable: true
  enhanced-mode: fake-ip
  fake-ip-filter: ['*.lan']
  nameserver: [119.29.29.29]
  proxy-server-nameserver: [223.5.5.5]
proxies:
  - {name: Monocloud_SS, type: ss, server: monoCloud_hostname, port: "monoCloud_port", cipher: "monoCloud_cipher", password: "monoCloud_password"}
proxy-groups:
  - name: Proxy
    type: select
    proxies: [Monocloud_SS]
{tunnel}
rules:
{Clash-rule}
- DOMAIN-SUFFIX,example.cn,DIRECT
- IP-CIDR,100.64.0.0/10,DIRECT
- GEOIP,CN,DIRECT
- MATCH,Proxy
"""


def node(name="Example", **kwargs):
    return Node(
        "service",
        name,
        kwargs.get("server", "node.example.invalid"),
        443,
        "aes-128-gcm",
        kwargs.get("password", "constructed-password"),
    )


def template_client(asset=TEMPLATE, **overrides):
    entry = {
        "name": "Clash_ss",
        "url": "https://static.example.invalid/Clash_ss",
        "size": len(asset),
        "sha256": hashlib.sha256(asset).hexdigest(),
    }
    entry.update(overrides)

    def handle(request):
        if request.url.path.endswith("update.json"):
            return httpx.Response(200, json={"templates": [entry]})
        return httpx.Response(200, content=asset)

    return httpx.Client(transport=httpx.MockTransport(handle))


class TemplateTests(unittest.TestCase):
    def test_fetches_manifest_resource_and_normalizes_known_placeholders(self):
        with template_client() as http:
            result = fetch_template(http, MonoCloudSettings())
        self.assertEqual(result["rules"][-1], "MATCH,Proxy")
        self.assertEqual(result["proxy-groups"][0]["name"], "Proxy")

    def test_rejects_digest_size_and_insecure_resource(self):
        for options in (
            {"sha256": "0" * 64},
            {"size": 0},
            {"url": "http://static.example.invalid/Clash_ss"},
        ):
            with self.subTest(options=options), template_client(**options) as http:
                with self.assertRaises(ValueError):
                    fetch_template(http, MonoCloudSettings())

    def test_rejects_invalid_or_changed_template_without_echoing_body(self):
        for content in (
            b"private-content: [",
            TEMPLATE.replace(b"{tunnel}", b"{unknown}"),
            b"[]",
            TEMPLATE.replace(b"- MATCH,Proxy", b"- MATCH,Unknown"),
        ):
            with self.subTest(content=content[:10]), template_client(content) as http:
                with self.assertRaises(ValueError) as caught:
                    fetch_template(http, MonoCloudSettings())
                self.assertNotIn("private-content", str(caught.exception))

    def test_network_and_manifest_errors_are_sanitized(self):
        for response in (
            httpx.Response(403, text="private-body"),
            httpx.Response(200, text="not-json"),
            httpx.Response(200, json={"templates": []}),
        ):
            with httpx.Client(
                transport=httpx.MockTransport(lambda r: response)
            ) as http:
                with self.assertRaises(ValueError) as caught:
                    fetch_template(http, MonoCloudSettings())
                self.assertNotIn("private-body", str(caught.exception))

    def test_malformed_manifest_fields_are_safe_errors(self):
        for entry in (
            None,
            123,
            {"name": "Clash_ss", "url": 42},
            {"name": "Clash_ss", "url": {"private": "value"}},
        ):
            with httpx.Client(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, json={"templates": [entry]})
                )
            ) as http:
                with self.assertRaises(ValueError):
                    fetch_template(http, MonoCloudSettings())

    def test_no_resolve_without_rule_fields_is_rejected(self):
        from monocloud_subscription.templates import validate_template

        with template_client() as http:
            template = fetch_template(http, MonoCloudSettings())
        template["rules"].insert(0, "no-resolve")
        with self.assertRaises(ValueError):
            validate_template(template)


class ClashTests(unittest.TestCase):
    def setUp(self):
        with template_client() as http:
            self.template = fetch_template(http, MonoCloudSettings())

    def render(self, nodes=None, tailscale=None):
        return yaml.safe_load(
            generate_clash(
                self.template,
                nodes or [node()],
                ClashSettings(),
                tailscale or TailscaleSettings(),
            )
        )

    def test_all_nodes_manual_selection_and_exact_rule_order(self):
        before = copy.deepcopy(self.template)
        result = self.render([node("One"), node("Two")])
        self.assertEqual(len(result["proxies"]), 2)
        self.assertEqual(
            result["proxy-groups"],
            [{"name": "Proxy", "type": "select", "proxies": ["One", "Two"]}],
        )
        self.assertEqual(result["rules"], before["rules"])
        self.assertEqual(self.template, before)
        self.assertEqual(result["mixed-port"], 7890)
        self.assertFalse(result["allow-lan"])
        self.assertNotIn("tailscale", str(result).lower())
        self.assertEqual(
            result["dns"]["proxy-server-nameserver"],
            before["dns"]["proxy-server-nameserver"],
        )

    def test_duplicate_and_reserved_names_are_unique_and_referenced(self):
        nodes = [
            node(n) for n in ("Proxy", "DIRECT", "Tailscale", "One", "One", "One (2)")
        ]
        result = self.render(nodes)
        names = [n["name"] for n in result["proxies"]]
        self.assertEqual(len(set(names)), len(nodes))
        self.assertTrue(set(names).isdisjoint({"Proxy", "DIRECT", "Tailscale"}))
        self.assertEqual(result["proxy-groups"][0]["proxies"], names)
        self.assertEqual(self.render(nodes), result)

    def test_yaml_special_characters_remain_node_data(self):
        password = 'secret: "#\\\n- injected: yes'
        name = "node:\n- MATCH,REJECT"
        result = self.render([node(name, password=password)])
        self.assertEqual(result["proxies"][0]["password"], password)
        self.assertEqual(result["proxies"][0]["name"], name)
        self.assertEqual(result["rules"], self.template["rules"])

    def test_no_nodes_rejects_generation(self):
        with self.assertRaisesRegex(ValueError, "nodes"):
            generate_clash(self.template, [], ClashSettings(), TailscaleSettings())

    def test_tailscale_routes_dns_bootstrap_and_persistent_client_state(self):
        settings = TailscaleSettings(
            enabled=True,
            hostname="example-phone",
            state_dir="tailscale-state",
            auth_key="constructed-key",
            routes=("192.168.50.0/24",),
        )
        result = self.render(tailscale=settings)
        ts = result["proxies"][-1]
        self.assertEqual(ts["type"], "tailscale")
        self.assertEqual(ts["dialer-proxy"], "Proxy")
        self.assertFalse(ts["ephemeral"])
        self.assertEqual(ts["state-dir"], "tailscale-state")
        self.assertEqual(ts["auth-key"], "constructed-key")
        self.assertTrue(ts["accept-routes"])
        self.assertEqual(
            result["rules"][-len(self.template["rules"]) :], self.template["rules"]
        )
        self.assertIn("IP-CIDR,100.64.0.0/10,Tailscale,no-resolve", result["rules"])
        self.assertIn(
            "IP-CIDR6,fd7a:115c:a1e0::/48,Tailscale,no-resolve", result["rules"]
        )
        self.assertIn("IP-CIDR,192.168.50.0/24,Tailscale,no-resolve", result["rules"])
        dns = result["dns"]
        self.assertEqual(dns["nameserver-policy"]["+.ts.net"], "ts://Tailscale")
        self.assertIn("+.ts.net", dns["fake-ip-filter"])
        self.assertTrue(dns["proxy-server-nameserver"])
        self.assertNotIn("ts://", str(dns["proxy-server-nameserver"]))
        self.assertNotIn("constructed-key", repr(settings))

    def test_tailscale_default_interactive_auth_and_disabled_omission(self):
        result = self.render(tailscale=TailscaleSettings(enabled=True))
        self.assertNotIn("auth-key", result["proxies"][-1])
        self.assertNotIn("exit-node", result["proxies"][-1])
        disabled = self.render(tailscale=TailscaleSettings(auth_key="unused"))
        self.assertNotIn("unused", str(disabled))
