"""Deployment-independent command-line entry point."""

import argparse
import os
import sys
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
            host = f"[{args.host}]" if ":" in args.host else args.host
            print(f"Listen URL: http://{host}:{args.port}", file=sys.stderr)
            if args.host not in ("127.0.0.1", "localhost", "::1"):
                print(
                    "WARNING: Remote HTTP does not encrypt account or management credentials. "
                    "Use an HTTPS reverse proxy before remote browser access.",
                    file=sys.stderr,
                )
            app = create_app(config, admin_password=management_password)
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
            return 0
        if args.command == "check":
            print(f"Configuration OK. Data directory: {config.data_dir}")
            return 0
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
