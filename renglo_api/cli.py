"""
CLI entrypoints for running Renglo API directly from the package.
"""

from __future__ import annotations

import argparse
import os

from renglo_api.app import run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Renglo API server.",
    )
    parser.add_argument("--host", default=os.getenv("RENGLO_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5000")),
    )
    parser.add_argument(
        "--config-path",
        default=os.getenv("RENGLO_CONFIG_PATH"),
        help="Optional path to env_config.py. Defaults to RENGLO_CONFIG_PATH when set.",
    )
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable Flask debug mode.",
    )
    parser.add_argument(
        "--no-debug",
        dest="debug",
        action="store_false",
        help="Disable Flask debug mode.",
    )
    parser.set_defaults(debug=os.getenv("RENGLO_DEBUG", "1") == "1")
    return parser


def main() -> None:
    args = _parser().parse_args()
    run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        config_path=args.config_path,
    )
