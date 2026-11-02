"""Deployment-independent command-line entry point."""

import argparse
import os
import sys
from ipaddress import IPv6Address
from pathlib import Path

from monocloud_subscription.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="monocloud-subscription",
        description="Run and configure the MonoCloud web service.",
    )
    parser.add_argument(
        "--config", type=Path, help="Path to a local TOML configuration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check configuration without modifying files.")
    web = commands.add_parser(
        "serve", help="Open the MonoCloud browser login interface."
    )
    web.add_argument(
        "--host", default="127.0.0.1", help="Listen address (default: loopback only)."
    )
    web.add_argument(
        "--port", type=int, default=8080, help="Listen port (default: 8080)."
    )
    args = parser.parse_args(argv)

    if args.config is None:
        parser.error(f"--config is required for {args.command}")
    try:
        config = load_config(args.config)
        if args.command == "serve":
            import uvicorn

            from monocloud_subscription.web import create_app

            bind_host = args.host.strip()
            if bind_host.startswith("[") and bind_host.endswith("]"):
                bind_host = bind_host[1:-1].strip()
            if not bind_host:
                raise ValueError("Host must not be empty.")
            try:
                if any(character in bind_host for character in "/?#@[]"):
                    raise ValueError
                if ":" in bind_host:
                    IPv6Address(bind_host)
            except ValueError:
                raise ValueError(
                    "Host must be a hostname or IP address without a scheme, port, or path."
                ) from None
            loopback = bind_host in ("127.0.0.1", "localhost", "::1")
            management_password = os.environ.get("MONOCLOUD_WEB_PASSWORD")
            if not loopback and not management_password:
                raise ValueError(
                    "Set MONOCLOUD_WEB_PASSWORD before binding beyond loopback."
                )
            if not 1 <= args.port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            host = f"[{bind_host}]" if ":" in bind_host else bind_host
            print(f"Listen URL: http://{host}:{args.port}", file=sys.stderr)
            if not loopback:
                print(
                    "WARNING: Remote HTTP does not encrypt account or management credentials. "
                    "Use an HTTPS reverse proxy before remote browser access.",
                    file=sys.stderr,
                )
            if bind_host in ("0.0.0.0", "::"):
                print(
                    "For browser access, use this machine's reachable address and the listen port.",
                    file=sys.stderr,
                )
            app = create_app(config, admin_password=management_password)
            uvicorn.run(app, host=bind_host, port=args.port, access_log=False)
            return 0
        if args.command == "check":
            print(f"Configuration OK. Data directory: {config.data_dir}")
            return 0
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
