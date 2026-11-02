"""Deployment-independent command-line entry point."""

import argparse
import getpass
import os
import warnings
from pathlib import Path

import httpx

from monocloud_subscription.config import load_config
from monocloud_subscription.monocloud import MonoCloudClient
from monocloud_subscription.tokens import TokenStore


def read_secret(prompt: str) -> str:
    """Refuse getpass's fallback to visible input when no terminal is available."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise ValueError("Use an interactive terminal with hidden input.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="monocloud-subscription",
        description="MonoCloud account and subscription tools.",
    )
    parser.add_argument(
        "--config", type=Path, help="Path to a local TOML configuration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check configuration without modifying files.")
    commands.add_parser(
        "import-token", help="Save an existing token using a hidden prompt."
    )
    commands.add_parser("login", help="Log in interactively and save the access token.")
    commands.add_parser(
        "plans", help="List Shadowsocks services available to the account."
    )
    web = commands.add_parser(
        "serve", help="Open the MonoCloud browser login interface."
    )
    web.add_argument(
        "--host", default="127.0.0.1", help="Listen address (default: loopback only)."
    )
    web.add_argument(
        "--port", type=int, default=8080, help="Listen port (default: 8080)."
    )
    nodes = commands.add_parser(
        "nodes", help="Discover Shadowsocks plans and fetch their nodes."
    )
    nodes.add_argument(
        "--plan-id",
        action="append",
        help="Service ID override; omit to discover all Shadowsocks plans.",
    )
    args = parser.parse_args(argv)

    if args.config is None:
        parser.error(f"--config is required for {args.command}")
    try:
        config = load_config(args.config)
        if args.command == "serve":
            import uvicorn

            from monocloud_subscription.web import create_app

            management_password = os.environ.get("MONOCLOUD_WEB_PASSWORD")
            if (
                args.host not in ("127.0.0.1", "localhost", "::1")
                and not management_password
            ):
                raise ValueError(
                    "Set MONOCLOUD_WEB_PASSWORD before binding beyond loopback."
                )
            if not 1 <= args.port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            app = create_app(config, admin_password=management_password)
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
            return 0
        if args.command == "check":
            print(f"Configuration OK. Data directory: {config.data_dir}")
            return 0
        store = TokenStore(config.token_file)
        if args.command == "import-token":
            store.save(read_secret("Access token: "))
            print("Access token saved.")
            return 0
        if args.command == "login":
            if not config.monocloud.client_id or not config.monocloud.client_secret:
                raise ValueError(
                    "Configure monocloud.client_id and client_secret for login."
                )
            username = input("Email: ").strip()
            password = read_secret("Password: ")
            with httpx.Client() as http:
                token = MonoCloudClient(config.monocloud, http).login(
                    username, password
                )
            store.save(token)
            print("Login successful. Access token saved.")
            return 0
        token = store.load()
        with httpx.Client() as http:
            api = MonoCloudClient(config.monocloud, http)
            if args.command == "plans":
                plans = api.fetch_plans(token)
                for plan in plans:
                    print(f"{plan.id}\t{plan.name}")
                print(f"Found {len(plans)} Shadowsocks plans.")
                return 0
            count = len(api.fetch_all_nodes(token, args.plan_id))
        print(
            f"Fetched {count} available nodes. Connection details were not printed or saved."
        )
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")
    except (EOFError, KeyboardInterrupt):
        parser.exit(2, "error: Input cancelled.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
