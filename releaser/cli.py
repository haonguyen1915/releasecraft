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
    parser.add_argument(
        "--pre", action="store_true", help="Use pre-release flow from config"
    )
    parser.add_argument(
        "--finalize", action="store_true", help="Convert current pre-release to stable"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--push", action="store_true", help="Push after commit/tag")
    parser.add_argument("--no-commit", action="store_true", help="Do not commit")
    parser.add_argument("--no-tag", action="store_true", help="Do not tag")
    parser.add_argument("--config", type=str, help="Path to config file")
    parser.add_argument(
        "--version-source",
        choices=["file", "local_tag", "remote_tag", "auto"],
        help="Source for current version: file|local_tag|remote_tag|auto",
    )

    # Release notes
    parser.add_argument(
        "--notes", type=str, help="Inline release notes (use \\n for newlines)"
    )
    parser.add_argument("--notes-file", type=str, help="Read release notes from file")
    parser.add_argument(
        "--changelog", action="store_true", help="Append notes to CHANGELOG.md"
    )
    parser.add_argument(
        "--changelog-file", type=str, help="Changelog path (default: CHANGELOG.md)"
    )


def add_init_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--yes", action="store_true", help="Accept defaults; non-interactive"
    )
    parser.add_argument(
        "--global",
        dest="global_cfg",
        action="store_true",
        help="Write to ~/.releaser/config.toml",
    )
    parser.add_argument("--path", type=str, help="Custom config file path")
    # Keep CLI minimal; full config is now always written by default.
    # Optionally prefill
    parser.add_argument(
        "--project-type",
        type=str,
        choices=["auto", "poetry", "setuptools", "npm"],
        help="Project type",
    )
    parser.add_argument("--tag-prefix", type=str, help="Default tag prefix (v)")
    parser.add_argument(
        "--use-native",
        dest="use_native",
        action="store_true",
        help="Use native tooling when available",
    )
    parser.add_argument(
        "--no-use-native",
        dest="use_native",
        action="store_false",
        help="Do not use native tooling",
    )
    parser.add_argument("--files", nargs="*", help="File targets PATH:selector ...")
    parser.add_argument(
        "--no-commit", action="store_true", help="Default: do not commit after bump"
    )
    parser.add_argument(
        "--no-tag", action="store_true", help="Default: do not tag after bump"
    )
    parser.add_argument("--push", action="store_true", help="Default: push after tag")
    parser.add_argument(
        "--pre-enable", action="store_true", help="Enable pre-release by default"
    )
    parser.add_argument(
        "--pre-channel", type=str, help="Default pre-release channel (rc)"
    )
    parser.add_argument(
        "--pre-apply", type=str, help="CSV branches allowed for pre-release"
    )
    parser.add_argument(
        "--pre-block", type=str, help="CSV branches blocked from pre-release"
    )
    parser.add_argument(
        "--pre-channel-map", type=str, help="Comma-separated branch:channel pairs"
    )
    parser.add_argument(
        "--bump-apply", type=str, help="CSV branches allowed to run bump"
    )
    parser.add_argument(
        "--bump-block", type=str, help="CSV branches blocked from running bump"
    )


def add_cache_arguments(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(
        dest="cache_action", help="Cache actions", metavar="ACTION"
    )

    # cache stats
    _stats_parser = subparsers.add_parser(
        "stats",
        help="Show cache statistics",
        description="Display AI cache statistics (size, entries, location)",
    )

    # cache clear
    clear_parser = subparsers.add_parser(
        "clear",
        help="Clear AI cache",
        description="Remove cached AI-generated release notes",
    )
    clear_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    clear_parser.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        help="Only clear entries older than N days",
    )
    clear_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )


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
    parser.add_argument(
        "--version", action="version", version=f"releaser {__version__}"
    )

    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", metavar="COMMAND"
    )

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

    # Commit Gen
    gen_parser = subparsers.add_parser(
        "commit-gen",
        help="Generate a Conventional Commit message from diffs",
        description="Analyze staged changes or specified files and propose a Conventional Commit message.",
    )
    gen_parser.add_argument(
        "--staged", action="store_true", help="Use staged changes (git diff --staged)"
    )
    gen_parser.add_argument(
        "--files", nargs="*", default=[], help="Additional files to include"
    )
    gen_parser.add_argument(
        "--ticket", type=str, help="Ticket reference to include as footer"
    )
    gen_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Automatically commit without prompting",
    )
    gen_parser.add_argument(
        "--no-ai",
        dest="no_ai",
        action="store_true",
        help="Disable AI and use heuristics only",
    )
    gen_parser.add_argument("--model", type=str, help="AI model (default from config)")
    gen_parser.add_argument(
        "--temperature", type=float, help="Sampling temperature (default from config)"
    )
    gen_parser.add_argument(
        "--max-tokens",
        dest="max_tokens",
        type=int,
        help="Max tokens (default from config)",
    )
    gen_parser.add_argument(
        "--history",
        type=int,
        help="Include last N commit subjects as context (default from config; 0 to disable)",
    )
    gen_parser.add_argument(
        "--system-prompt-file", type=str, help="Custom system prompt file"
    )
    gen_parser.add_argument(
        "--user-prompt-file", type=str, help="Custom user prompt template file"
    )
    gen_parser.add_argument(
        "--output", type=str, help="Write message to file (default: stdout)"
    )
    gen_parser.add_argument("--config", type=str, help="Path to config file")

    # Commit Lint
    lint_parser = subparsers.add_parser(
        "commit-lint",
        help="Validate commit message against Conventional Commits",
        description="Validate a commit message file or .git/COMMIT_EDITMSG using Conventional Commit rules.",
    )
    lint_parser.add_argument(
        "files", nargs="*", help="Path to commit message file (from pre-commit)"
    )
    lint_parser.add_argument(
        "--config", type=str, help="Path to config file (optional)"
    )
    lint_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # Cache
    cache_parser = subparsers.add_parser(
        "cache",
        help="Manage AI cache",
        description="View statistics and clear cached AI-generated release notes",
    )
    add_cache_arguments(cache_parser)

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


def handle_cache_command(args: argparse.Namespace) -> int:
    """Handle cache subcommands (stats, clear)."""
    try:
        from .ai.cache import get_cache_stats, clear_cache

        # Check if action was specified
        if not getattr(args, "cache_action", None):
            logger.error("Please specify an action: 'stats' or 'clear'")
            logger.info("Usage: releaser cache {stats|clear}")
            return 1

        if args.cache_action == "stats":
            # Show cache statistics
            stats = get_cache_stats()
            console.print()
            console.print("[bold cyan]AI Cache Statistics[/bold cyan]")
            console.print(f"  Location: {stats['cache_dir']}")
            console.print(f"  Total entries: {stats['total_entries']}")

            # Format size nicely
            size_bytes = stats["total_size_bytes"]
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

            console.print(f"  Total size: {size_str}")
            console.print()
            return 0

        elif args.cache_action == "clear":
            # Clear cache
            stats = get_cache_stats()

            if stats["total_entries"] == 0:
                logger.info("Cache is already empty")
                return 0

            # Show what will be deleted
            if args.older_than:
                logger.info(
                    f"Clearing cache entries older than {args.older_than} days..."
                )
            else:
                logger.info(f"Clearing all {stats['total_entries']} cache entries...")

            # Confirm unless --force
            if not args.force:
                from .console import prompt_choice

                choice = prompt_choice(
                    "Are you sure?", ["Yes, clear cache", "No, cancel"]
                )
                if choice != "Yes, clear cache":
                    logger.info("Cancelled")
                    return 0

            # Perform deletion
            deleted = clear_cache(max_age_days=args.older_than)

            if args.verbose:
                logger.info(f"Successfully deleted {deleted} cache entries")

            return 0

        else:
            logger.error(f"Unknown cache action: {args.cache_action}")
            return 1

    except Exception as e:
        logger.error(f"Cache command failed: {e}")
        return 1

    # Removed redundant wrappers for draft/greeting/log/version to keep CLI surface minimal.


def main(argv: Optional[list[str]] = None) -> int:
    try:
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
        if args.command == "commit-gen":
            try:
                from .commit_gen import run as run_gen

                return run_gen(args)
            except Exception as e:
                logger.error(f"Commit message generation failed: {e}")
                return 1
        if args.command == "commit-lint":
            try:
                from .commit_lint import run as run_lint

                return run_lint(args)
            except Exception as e:
                logger.error(f"Commit lint failed: {e}")
                return 1
        if args.command == "cache":
            return handle_cache_command(args)

        logger.error(f"Unknown command: {args.command}")
        return 1
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        return 130  # Standard exit code for SIGINT


if __name__ == "__main__":
    sys.exit(main())
