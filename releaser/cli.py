#!/usr/bin/env python3
"""
Main CLI interface for the releaser package.

This module provides a unified command-line interface that combines all
releaser functionality into a single command with subcommands.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from .console import console, logger, print_version_header

try:
    from . import __version__
    from .drafter import ReleaseGenerator
    from .greeting import main as greeting_main
    from .log.cli_parser import setup_argument_parser as setup_log_parser
    from .log.modes import (
        list_kubernetes_namespaces,
        list_kubernetes_pods,
        run_command_mode,
        run_interactive_mode,
        run_kubectl_mode,
    )
except ImportError:
    __version__ = "0.1.0"

    # Import directly for script execution
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from releaser.drafter import ReleaseGenerator
    from releaser.greeting import main as greeting_main
    from releaser.log.cli_parser import setup_argument_parser as setup_log_parser
    from releaser.log.modes import (
        list_kubernetes_namespaces,
        list_kubernetes_pods,
        run_command_mode,
        run_interactive_mode,
        run_kubectl_mode,
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser for the releaser CLI."""
    parser = argparse.ArgumentParser(
        prog="releaser",
        description="A CLI tool for generating releases and changelogs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
        epilog="""
Examples:
  releaser draft                    # Generate a release draft
  releaser draft -n                 # Preview release without making changes
  releaser draft --manual           # Manually specify version
  releaser draft -r                 # Create release with merge request
  releaser draft -d -s             # Check and auto-squash duplicate commits
  releaser draft -t main            # Create MR targeting main branch
  releaser draft -a                 # Auto-release with MR and GitLab release
  releaser draft --no-interactive   # Fully automated mode without prompts
  releaser draft --force            # Force execution ignoring warnings
  releaser greeting                 # Print a greeting message
  releaser greeting -f              # Print a fun greeting
  releaser log                      # Stream logs to WebSocket server
  releaser log --kubectl -p my-pod  # Stream kubectl logs for a pod
  releaser log --cmd ls -l          # Stream local command output
  releaser version                  # Show version information
        """,
    )

    # Add global version flag
    parser.add_argument(
        "--version",
        action="version",
        version=f"releaser {__version__}",
        help="Show version information and exit",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        metavar="COMMAND",
    )

    # Draft command
    draft_parser = subparsers.add_parser(
        "draft",
        help="Generate a release draft with changelog and version updates",
        description="Generate a release draft with changelog and version updates",
    )
    add_draft_arguments(draft_parser)

    # Greeting command
    greeting_parser = subparsers.add_parser(
        "greeting",
        help="Print a greeting message",
        description="Print a simple greeting message with optional fun mode",
    )
    greeting_parser.add_argument(
        "-f",
        "--fun",
        action="store_true",
        help="Print a fun and enthusiastic greeting!",
    )

    # Log command
    log_parser = subparsers.add_parser(
        "log",
        help="Stream logs to WebSocket server",
        description="Stream logs to WebSocket server with support for kubectl logs and local commands",
    )
    add_log_arguments(log_parser)

    # Bump command
    bump_parser = subparsers.add_parser(
        "bump",
        help="Interactively bump version or via flags",
        description=(
            "Interactively bump the project version (auto/manual) with optional pre-release and release notes."
        ),
    )
    add_bump_arguments(bump_parser)

    # Version command
    _ = subparsers.add_parser(
        "version",
        help="Show version information",
        description="Display the current version of releaser",
    )

    return parser


def add_bump_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the bump command (minimal set)."""
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


def add_draft_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments specific to the draft command."""
    # Boolean flags (True/False)
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be generated without making changes",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        default=False,
        help="Manually specify version (default: auto-determine from git tags)",
    )
    parser.add_argument(
        "-r",
        "--create-mr",
        action="store_true",
        default=False,
        help="Create a new branch and merge request with the release changes",
    )
    parser.add_argument(
        "-d",
        "--check-commit-duplicates",
        action="store_true",
        default=False,
        help="Check for duplicate commit messages and display them in a table",
    )
    parser.add_argument(
        "-s",
        "--squash-commit-duplicates",
        action="store_true",
        default=False,
        help="Automatically squash duplicate commits (requires --check-commit-duplicates)",
    )
    parser.add_argument(
        "-a",
        "--auto-release",
        action="store_true",
        default=False,
        help="Automatically create release branch, MR, and GitLab release (includes --create-mr functionality)",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        default=False,
        help="Run in fully automated mode without any prompts or confirmations",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force execution even with warnings (uncommitted changes, failed squash, etc.)",
    )

    # String arguments
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        default="",
        help="Target branch for the merge request (default: current branch)",
    )
    parser.add_argument(
        "--gitlab-token",
        type=str,
        default="",
        help="GitLab API token (can also be set via GITLAB_TOKEN environment variable)",
    )


def add_log_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments specific to the log command."""
    # Connection settings (new names with backward-compatible aliases)
    parser.add_argument(
        "--server",
        "--ws-server",
        dest="server",
        default="ws://localhost:8000/ws/client",
        help="Log server URL (ws://... or http://...). --ws-server is deprecated alias",
    )
    parser.add_argument(
        "--service-name",
        "--service",
        dest="service_name",
        default=None,
        help="Service name identifier (default: auto-generated). --service is deprecated alias",
    )
    parser.add_argument(
        "--auth-token",
        "--token",
        dest="auth_token",
        default="secret-token-change-me",
        help="Authentication token. --token is deprecated alias",
    )
    parser.add_argument(
        "--no-echo", action="store_true", help="Disable echoing to console"
    )

    # Mutually exclusive: kubectl vs command vs interactive
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--kubectl",
        action="store_true",
        help="Capture kubectl logs instead of terminal output",
    )
    group.add_argument(
        "--command",
        "--cmd",
        dest="cmd",
        nargs=argparse.REMAINDER,
        help="Run a local command and stream its output to the log server. MUST be the last option; everything after it is treated as the command (e.g., --command ls -l /). --cmd is deprecated alias",
    )

    # Kubernetes specific arguments
    parser.add_argument("--namespace", "-n", help="Kubernetes namespace")
    parser.add_argument("--pod", "-p", help="Pod name for kubectl logs")
    parser.add_argument("--container", "-c", help="Container name (optional)")
    parser.add_argument(
        "--tail-lines",
        "--tail",
        dest="tail_lines",
        type=int,
        help="Number of lines to tail (alias: --tail)",
    )
    parser.add_argument(
        "--since",
        help="Show logs since time/duration (e.g., 1h, 2d, 2023-01-01T00:00:00Z)",
    )
    parser.add_argument(
        "--list-pods", action="store_true", help="List available pods and exit"
    )
    parser.add_argument(
        "--list-namespaces",
        action="store_true",
        help="List available namespaces and exit",
    )

    # Server identification and resource limits
    parser.add_argument("--server-name", help="Logical server name for identification")
    parser.add_argument(
        "--server-source",
        choices=["local", "k8s"],
        default="local",
        help="Server source type (default: local)",
    )
    parser.add_argument(
        "--max-cpu-cores", type=float, help="Override detected CPU core limit"
    )
    parser.add_argument(
        "--max-memory",
        "--max-memory-bytes",
        dest="max_memory",
        type=str,
        help="Override detected memory limit (e.g., 16GB, 512M). --max-memory-bytes is deprecated alias",
    )
    parser.add_argument("--gpu-count", type=int, help="Override detected GPU count")
    parser.add_argument(
        "--max-gpu-memory",
        "--max-gpu-memory-bytes",
        dest="max_gpu_memory",
        type=int,
        help="Override detected GPU memory in bytes. --max-gpu-memory-bytes is deprecated alias",
    )

    # Public tunnel options (new)
    parser.add_argument(
        "--expose",
        action="store_true",
        help="Expose local service publicly via Bore tunnel",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Local port to expose (default: 8000)"
    )
    parser.add_argument(
        "--tunnel-secret", type=str, help="Shared secret for Bore tunnel authentication"
    )
    parser.add_argument(
        "--tunnel-host",
        type=str,
        default="bore.pub",
        help="Bore tunnel server host (default: bore.pub)",
    )
    parser.add_argument(
        "--bore-executable",
        type=str,
        default="bore",
        help="Path to bore executable (default: bore)",
    )
    parser.add_argument(
        "--http-server",
        action="store_true",
        help="Start built-in HTTP log endpoint when exposing",
    )

    # Kubernetes events streaming control
    parser.add_argument(
        "--no-k8s-events",
        action="store_true",
        help="Disable streaming Kubernetes Warning events when server source is k8s",
    )


def handle_draft_command(args: argparse.Namespace) -> int:
    """Handle the draft command."""
    generator = ReleaseGenerator()

    # Set generator attributes based on arguments
    generator.dry_run = args.dry_run
    generator.mode = "manual" if args.manual else "auto"
    generator.create_mr = args.create_mr
    generator.check_duplicates = args.check_commit_duplicates
    generator.auto_squash_duplicates = args.squash_commit_duplicates
    generator.auto_release = args.auto_release
    generator.no_interactive = args.no_interactive
    generator.force = args.force
    generator.gitlab_token = args.gitlab_token

    # Validate squash requires check-commit-duplicates
    if args.squash_commit_duplicates and not args.check_commit_duplicates:
        logger.error("--squash-commit-duplicates requires --check-commit-duplicates")
        return 1

    # Validate no-interactive mode constraints
    if args.no_interactive:
        # Manual mode cannot be used with no-interactive
        if args.manual:
            logger.error("Manual mode (--manual) cannot be used with --no-interactive")
            return 1

        # In automated mode, we should enable auto-release by default if not already set
        if not generator.auto_release and not args.create_mr:
            generator.auto_release = True
            generator.create_mr = True

    # Auto-release now automatically enables create-mr
    if args.auto_release:
        generator.create_mr = True

    # Handle MR target branch logic
    if generator.create_mr:
        if args.target:
            generator.mr_target_branch = args.target
        else:
            # Will be set to current branch in main() method
            generator.mr_target_branch = ""

    try:
        generator.main()
        return 0
    except Exception as e:
        logger.error(str(e))
        return 1


def handle_greeting_command(args: argparse.Namespace) -> int:
    """Handle the greeting command."""
    try:
        # Temporarily modify sys.argv to pass the fun flag to greeting.main()
        original_argv = sys.argv.copy()
        sys.argv = ["greeting"]
        if args.fun:
            sys.argv.append("--fun")

        greeting_main()
        return 0
    except Exception as e:
        logger.error(str(e))
        return 1
    finally:
        # Restore original argv
        sys.argv = original_argv


def handle_log_command(args: argparse.Namespace) -> int:
    """Handle the log command."""
    try:
        # Normalize deprecated argument aliases
        _normalize_log_args(args)
        
        # Handle list operations first
        if getattr(args, "list_pods", False):
            list_kubernetes_pods(getattr(args, "namespace", None))
            return 0
        
        if getattr(args, "list_namespaces", False):
            list_kubernetes_namespaces()
            return 0
        
        # Handle different execution modes
        if getattr(args, "kubectl", False):
            run_kubectl_mode(args)
        elif getattr(args, "cmd", None):
            # Set command for modes.py compatibility
            args.command = args.cmd
            run_command_mode(args)
        else:
            run_interactive_mode(args)
        
        return 0
    except Exception as e:
        logger.error(f"Log command failed: {e}")
        return 1


def _normalize_log_args(args: argparse.Namespace) -> None:
    """Normalize deprecated argument aliases for backward compatibility."""
    # Handle deprecated server argument alias
    if hasattr(args, "ws_server") and args.ws_server and not getattr(args, "server", None):
        args.server = args.ws_server
    
    # Handle deprecated service name alias
    if hasattr(args, "service") and args.service and not getattr(args, "service_name", None):
        args.service_name = args.service
    
    # Handle deprecated auth token alias
    if hasattr(args, "token") and args.token and not getattr(args, "auth_token", None):
        args.auth_token = args.token
    
    # Handle deprecated tail lines alias
    if hasattr(args, "tail") and args.tail and not getattr(args, "tail_lines", None):
        args.tail_lines = args.tail
    
    # Handle deprecated memory aliases
    if hasattr(args, "max_memory_bytes") and args.max_memory_bytes and not getattr(args, "max_memory", None):
        args.max_memory = args.max_memory_bytes
    
    # Handle deprecated GPU memory alias
    if hasattr(args, "max_gpu_memory_bytes") and args.max_gpu_memory_bytes and not getattr(args, "max_gpu_memory", None):
        args.max_gpu_memory = args.max_gpu_memory_bytes
    
    # Handle deprecated command alias
    if hasattr(args, "command") and args.command and not getattr(args, "cmd", None):
        args.cmd = args.command


def handle_version_command(args: argparse.Namespace) -> int:
    """Handle the version command."""
    try:
        console.print(f"[bold blue]releaser[/bold blue] version [bright_green]{__version__}[/bright_green]")
        return 0
    except Exception as e:
        logger.error(str(e))
        return 1


def handle_bump_command(args: argparse.Namespace) -> int:
    """Handle the bump command."""
    try:
        from .bump.flow import run as run_bump
        return run_bump(args)
    except Exception as e:
        logger.error(f"Bump failed: {e}")
        return 1


def main(args: Optional[list[str]] = None) -> int:
    """
    Main entry point for the releaser CLI.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    print_version_header()

    parser = create_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        # Gracefully handle argparse errors (e.g., unknown subcommand) by returning non-zero
        return 1

    if not parsed_args.command:
        parser.print_help()
        return 1

    if parsed_args.command == "draft":
        return handle_draft_command(parsed_args)
    elif parsed_args.command == "greeting":
        return handle_greeting_command(parsed_args)
    elif parsed_args.command == "log":
        return handle_log_command(parsed_args)
    elif parsed_args.command == "bump":
        return handle_bump_command(parsed_args)
    elif parsed_args.command == "version":
        return handle_version_command(parsed_args)
    else:
        logger.error(f"Unknown command: {parsed_args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
