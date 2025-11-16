#!/usr/bin/env python3
"""
Log streaming client for capturing and forwarding logs to a central server.

This client can:
- Stream stdout/stderr from local processes
- Capture kubectl logs from Kubernetes pods
- Expose services publicly via Bore tunneling
- Monitor system resources and send metrics

This is the main entry point that orchestrates all log client functionality.
"""

from .cli_parser import setup_argument_parser
from .modes import (
    list_kubernetes_namespaces,
    list_kubernetes_pods,
    run_command_mode,
    run_interactive_mode,
    run_kubectl_mode,
)


def main() -> None:
    """Main entry point."""
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Handle list operations
    if args.list_pods:
        list_kubernetes_pods(args.namespace)
        return

    if args.list_namespaces:
        list_kubernetes_namespaces()
        return

    # Handle different execution modes
    if args.kubectl:
        run_kubectl_mode(args)
    elif args.command:
        run_command_mode(args)
    else:
        run_interactive_mode(args)


if __name__ == "__main__":
    main()
