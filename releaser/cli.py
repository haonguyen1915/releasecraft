#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from typing import Optional

from .console import console, logger, print_version_header


def add_bump_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manual", type=str, help="Set exact version (bypasses auto)")
    parser.add_argument(
        "--type",
        choices=["major", "minor", "patch"],
        help="Force bump type (overrides auto)",
    )
    parser.add_argument("--pre", action="store_true", help="Use pre-release flow from config")
    parser.add_argument(
        "--finalize", action="store_true", help="Convert current pre-release to stable"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--push", action="store_true", help="Push after commit/tag")
    parser.add_argument("--no-commit", action="store_true", help="Do not commit")
    parser.add_argument("--no-tag", action="store_true", help="Do not tag")
    parser.add_argument("--config", type=str, help="Path to config file")

    # Release notes
    parser.add_argument("--notes", type=str, help="Inline release notes (use \\n for newlines)")
    parser.add_argument("--notes-file", type=str, help="Read release notes from file")
    parser.add_argument("--changelog", action="store_true", help="Append notes to CHANGELOG.md")
    parser.add_argument("--changelog-file", type=str, help="Changelog path (default: CHANGELOG.md)")


def add_init_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", action="store_true", help="Accept defaults; non-interactive")
    parser.add_argument("--global", dest="global_cfg", action="store_true", help="Write to ~/.releaser/config.toml")
    parser.add_argument("--path", type=str, help="Custom config file path")
    # Optionally prefill
    parser.add_argument("--project-type", type=str, choices=["auto", "poetry", "setuptools", "npm"], help="Project type")
    parser.add_argument("--tag-prefix", type=str, help="Default tag prefix (v)")
    parser.add_argument("--use-native", dest="use_native", action="store_true", help="Use native tooling when available")
    parser.add_argument("--no-use-native", dest="use_native", action="store_false", help="Do not use native tooling")
    parser.add_argument("--files", nargs="*", help="File targets PATH:selector ...")
    parser.add_argument("--no-commit", action="store_true", help="Default: do not commit after bump")
    parser.add_argument("--no-tag", action="store_true", help="Default: do not tag after bump")
    parser.add_argument("--push", action="store_true", help="Default: push after tag")
    parser.add_argument("--pre-enable", action="store_true", help="Enable pre-release by default")
    parser.add_argument("--pre-channel", type=str, help="Default pre-release channel (rc)")
    parser.add_argument("--pre-apply", type=str, help="CSV branches allowed for pre-release")
    parser.add_argument("--pre-block", type=str, help="CSV branches blocked from pre-release")
    parser.add_argument("--pre-channel-map", type=str, help="Comma-separated branch:channel pairs")
    parser.add_argument("--bump-apply", type=str, help="CSV branches allowed to run bump")
    parser.add_argument("--bump-block", type=str, help="CSV branches blocked from running bump")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="releaser",
        description="Releaser CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    # Version flag – try to read from package metadata via releaser.__init__
    try:
        from . import __version__
    except Exception:
        __version__ = "0.0.0"
    parser.add_argument("--version", action="version", version=f"releaser {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands", metavar="COMMAND")

    # Bump
    bump_parser = subparsers.add_parser(
        "bump",
        help="Interactively bump version or via flags",
        description="Interactively bump version (auto/manual) with optional pre-release and release notes.",
    )
    add_bump_arguments(bump_parser)

    # Init
    init_parser = subparsers.add_parser(
        "init",
        help="Create a .releaser.toml config interactively",
        description="Scaffold a minimal .releaser.toml (or ~/.releaser/config.toml) with sensible defaults",
    )
    add_init_arguments(init_parser)

    # Keep CLI minimal: only bump and init are exposed here.
    return parser


def handle_bump_command(args: argparse.Namespace) -> int:
    try:
        from .bump.flow import run as run_bump
        return run_bump(args)
    except Exception as e:
        logger.error(f"Bump failed: {e}")
        return 1


def handle_init_command(args: argparse.Namespace) -> int:
    try:
        from .init_cmd import run as run_init
        return run_init(args)
    except Exception as e:
        logger.error(f"Init failed: {e}")
        return 1


    # Removed redundant wrappers for draft/greeting/log/version to keep CLI surface minimal.


def main(argv: Optional[list[str]] = None) -> int:
    print_version_header()
    parser = create_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    if not getattr(args, "command", None):
        parser.print_help()
        return 1

    if args.command == "bump":
        return handle_bump_command(args)
    if args.command == "init":
        return handle_init_command(args)
    # Only bump and init supported here. Other utilities have dedicated entry points.

    logger.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
