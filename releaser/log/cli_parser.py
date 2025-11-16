#!/usr/bin/env python3
"""
Command line argument parser for the log client.

This module provides the argument parser configuration for all log client options
including connection settings, execution modes, Kubernetes options, and tunnel settings.
"""

import argparse


def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Stream logs to a central log server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream current terminal output
  %(prog)s --server ws://logserver:8000

  # Run command and stream its output  
  %(prog)s --command ls -la /tmp

  # Stream kubectl logs
  %(prog)s --kubectl --pod my-pod --namespace production

  # Expose local service publicly
  %(prog)s --expose --port 3000 --tunnel-secret mysecret
        """,
    )

    # Connection settings
    parser.add_argument(
        "--server",
        default="ws://localhost:8000/ws/client",
        help="Log server WebSocket URL (default: ws://localhost:8000/ws/client)",
    )
    parser.add_argument(
        "--service-name", help="Service name identifier (default: auto-generated)"
    )
    parser.add_argument(
        "--auth-token",
        default="secret-token-change-me",
        help="Authentication token for server (default: secret-token-change-me)",
    )
    parser.add_argument(
        "--no-echo", action="store_true", help="Disable local console output echoing"
    )

    # Execution modes
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        help="Execute command and stream its output (e.g., --command ls -la)",
    )
    parser.add_argument(
        "--kubectl",
        action="store_true",
        help="Stream kubectl logs instead of terminal output",
    )

    # Kubernetes options
    parser.add_argument(
        "--namespace", "-n", help="Kubernetes namespace for kubectl operations"
    )
    parser.add_argument("--pod", "-p", help="Pod name for kubectl logs")
    parser.add_argument(
        "--container", "-c", help="Container name within pod (optional)"
    )
    parser.add_argument(
        "--tail-lines", type=int, help="Number of log lines to tail from end"
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

    # Server identification
    parser.add_argument("--server-name", help="Logical server name for identification")
    parser.add_argument(
        "--server-source",
        choices=["local", "k8s"],
        default="local",
        help="Server source type (default: local)",
    )

    # Resource limits
    parser.add_argument(
        "--max-cpu-cores", type=float, help="Override detected CPU core limit"
    )
    parser.add_argument(
        "--max-memory",
        type=str,
        help="Override detected memory limit (e.g., 16GB, 512M)",
    )
    parser.add_argument("--gpu-count", type=int, help="Override detected GPU count")
    parser.add_argument(
        "--max-gpu-memory", type=int, help="Override detected GPU memory in bytes"
    )

    # Public tunnel options
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

    # Kubernetes events streaming
    parser.add_argument(
        "--no-k8s-events",
        action="store_true",
        help="Disable streaming Kubernetes Warning events when server source is k8s",
    )

    return parser
