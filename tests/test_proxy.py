"""Verify the environment proxy support used by production HTTP clients."""

import unittest
from unittest.mock import patch

import httpx


class ProxyEnvironmentTests(unittest.TestCase):
    def test_socks_environment_does_not_break_http_client_creation(self):
        # Construction must work without making a network request.
        with patch.dict(
            "os.environ", {"ALL_PROXY": "socks5://127.0.0.1:9"}, clear=True
        ):
            with httpx.Client():
                pass
