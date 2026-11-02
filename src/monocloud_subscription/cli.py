"""Deployment-independent command-line entry point."""

import argparse
from pathlib import Path

from monocloud_subscription.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="monocloud-subscription",
        description="MonoCloud subscription tools (initial project foundation).",
    )
    parser.add_argument(
        "--config", type=Path, help="Path to a local TOML configuration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check configuration without modifying files.")
    args = parser.parse_args(argv)

    if args.config is None:
        parser.error("--config is required for check")
    try:
        config = load_config(args.config)
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")

    print(f"Configuration OK. Data directory: {config.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
