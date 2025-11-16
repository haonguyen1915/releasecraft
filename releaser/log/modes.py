#!/usr/bin/env python3
"""
Execution mode functions for the log client.

This module provides different execution modes:
- Interactive terminal streaming
- kubectl log streaming  
- Command execution with log streaming
- Utility functions for listing pods/namespaces
"""

import argparse
import asyncio
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, Optional, Callable

from ..console import console, logger
from .streaming import LogStreamingClient, LogStreamer
from .tunnel import PublicTunnelService
from .utils import get_system_resources


def list_kubernetes_pods(namespace: Optional[str] = None) -> None:
    """List available Kubernetes pods."""
    streamer = LogStreamer()
    pods = streamer.list_pods(namespace)

    if pods:
        namespace_info = f" in namespace '{namespace}'" if namespace else ""
        console.print(f"[bold blue]Available pods{namespace_info}:[/bold blue]")
        for pod in pods:
            console.print(f"  • [cyan]{pod}[/cyan]")
    else:
        console.print("[yellow]No pods found[/yellow]")


def list_kubernetes_namespaces() -> None:
    """List available Kubernetes namespaces."""
    streamer = LogStreamer()
    namespaces = streamer.list_namespaces()

    if namespaces:
        console.print("[bold blue]Available namespaces:[/bold blue]")
        for namespace in namespaces:
            console.print(f"  • [cyan]{namespace}[/cyan]")
    else:
        console.print("[yellow]No namespaces found[/yellow]")


def run_kubectl_mode(args: argparse.Namespace) -> None:
    """Run in kubectl log streaming mode."""
    if not args.pod:
        logger.error("--pod is required when using --kubectl mode")
        return

    # Determine service name
    service_name = args.service_name or f"kubectl-{args.pod}"

    # Collect system resources
    system_resources = get_system_resources(args)
    server_info = {
        "source": "k8s" if args.namespace or args.container else args.server_source,
        "k8s": {
            "namespace": args.namespace,
            "pod": args.pod,
            "container": args.container,
        },
        "maxResources": system_resources,
    }

    # Create log streamer
    with LogStreamer(
        server_url=args.server,
        service_name=service_name,
        auth_token=args.auth_token,
        echo_enabled=not args.no_echo,
        server_name=args.server_name,
        server_info=server_info,
    ) as streamer:
        # Set up public tunnel if requested
        tunnel_service = None
        if args.expose:
            tunnel_service = _setup_tunnel_service(args, streamer)
            if tunnel_service is None:
                logger.error("Aborting: Bore is required but not installed.")
                return

        logger.info(f"Starting kubectl logs for pod: {args.pod}")
        if args.namespace:
            logger.info(f"Namespace: {args.namespace}")
        if args.container:
            logger.info(f"Container: {args.container}")
        console.print("[dim]Press Ctrl+C to stop[/dim]")

        # Start kubectl log capture
        success = streamer.start_kubectl_logs(
            namespace=args.namespace,
            pod_name=args.pod,
            container=args.container,
            follow=True,
            tail_lines=args.tail_lines,
            since=args.since,
        )

        if not success:
            logger.error("Failed to start kubectl log capture")
            return

        # Also stream cluster Warning events across namespaces unless disabled
        try:
            if (
                args.server_source == "k8s" or args.namespace or args.container
            ) and not args.no_k8s_events:
                streamer.start_k8s_events(types=["Warning"], all_namespaces=True)
        except Exception:
            pass

        try:
            # Keep running until interrupted
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping kubectl log capture...[/yellow]")
        finally:
            if tunnel_service:
                tunnel_service.stop()


def run_interactive_mode(args: argparse.Namespace) -> None:
    """Run in interactive terminal streaming mode."""
    # Collect system resources
    system_resources = get_system_resources(args)
    server_info = {"source": args.server_source, "maxResources": system_resources}

    # Create streaming client
    client = LogStreamingClient(
        server_url=args.server,
        service_name=args.service_name,
        auth_token=args.auth_token,
        echo_enabled=not args.no_echo,
        server_name=args.server_name,
        server_info=server_info,
    )

    # Set up public tunnel if requested
    tunnel_service = None
    if args.expose:
        tunnel_service = _setup_tunnel_service(args, client)
        if tunnel_service is None:
            logger.error("Aborting: Bore is required but not installed.")
            return

    # Set up signal handler for graceful shutdown
    def signal_handler(signum, frame):
        console.print("\n[yellow]Stopping log client...[/yellow]")
        client.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Run the client
    try:
        # If running in k8s source, start Warning events streaming unless disabled
        if args.server_source == "k8s" and not args.no_k8s_events:
            try:
                client.start_k8s_events(types=["Warning"], all_namespaces=True)
            except Exception:
                pass
        asyncio.run(client.run())
    finally:
        if tunnel_service:
            tunnel_service.stop()


def run_command_mode(args: argparse.Namespace) -> None:
    """Run a command and stream its output."""
    if not args.command:
        logger.error("--command requires a command to execute")
        return

    # Determine service name
    service_name = args.service_name or f"cmd-{'-'.join(args.command)}"

    # Collect system resources
    system_resources = get_system_resources(args)
    server_info = {"source": args.server_source, "maxResources": system_resources}

    # Create log streamer
    with LogStreamer(
        server_url=args.server,
        service_name=service_name,
        auth_token=args.auth_token,
        echo_enabled=not args.no_echo,
        server_name=args.server_name,
        server_info=server_info,
    ) as streamer:
        # Set up public tunnel if requested
        tunnel_service = None
        if args.expose:
            tunnel_service = _setup_tunnel_service(args, streamer)
            if tunnel_service is None:
                logger.error("Aborting: Bore is required but not installed.")
                return

        logger.info(f"Executing command: {' '.join(args.command)}")
        console.print("[dim]Press Ctrl+C to stop[/dim]")

        try:
            # If running in k8s source, start Warning events streaming unless disabled
            try:
                if args.server_source == "k8s" and not args.no_k8s_events:
                    streamer.start_k8s_events(types=["Warning"], all_namespaces=True)
            except Exception:
                pass
            # Start the command process
            process = subprocess.Popen(
                args.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            # Capture process output
            streamer.capture_subprocess_output(process)

            # Wait for process completion
            while process.poll() is None:
                time.sleep(0.2)

        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping command execution...[/yellow]")
            if "process" in locals():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        finally:
            if tunnel_service:
                tunnel_service.stop()


def _setup_tunnel_service(
    args: argparse.Namespace, client_or_streamer
) -> Optional[PublicTunnelService]:
    """Set up public tunnel service with log callback."""
    log_callback_fn: Optional[Callable[[str, str], None]] = None

    # Set up log callback if HTTP server is enabled
    if args.http_server:

        def log_callback(message: str, level: str = "INFO") -> None:
            if hasattr(client_or_streamer, "log_queue"):
                # Direct client
                client_or_streamer.log_queue.put(
                    {
                        "type": "log",
                        "level": level,
                        "message": message,
                        "source": "public",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            else:
                # Streamer wrapper
                client_or_streamer.client.log_queue.put(
                    {
                        "type": "log",
                        "level": level,
                        "message": message,
                        "source": "public",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    # Set up tunnel info callback
    def tunnel_info_callback(tunnel_info: Dict) -> None:
        try:
            # Add service/server info for UI mapping
            enriched_info = dict(tunnel_info)
            if hasattr(client_or_streamer, "service_name"):
                # Direct client
                enriched_info["serviceName"] = client_or_streamer.service_name
                enriched_info["serverName"] = client_or_streamer.server_name
                client_or_streamer.public_tunnel_info = enriched_info
            else:
                # Streamer wrapper
                enriched_info["serviceName"] = client_or_streamer.client.service_name
                enriched_info["serverName"] = client_or_streamer.client.server_name
                client_or_streamer.client.public_tunnel_info = enriched_info
        except Exception:
            pass

    # Create and start tunnel service
    # Use the created callback if defined
    log_callback_fn = locals().get("log_callback", None)

    tunnel_service = PublicTunnelService(
        port=args.port,
        log_callback=log_callback_fn,
        tunnel_enabled=True,
        tunnel_host=args.tunnel_host,
        bore_executable=args.bore_executable,
        tunnel_secret=args.tunnel_secret,
        start_http_server=args.http_server,
        tunnel_info_callback=tunnel_info_callback,
        enable_port_forward=(args.server_source == "k8s"),
        k8s_namespace=getattr(args, "namespace", None),
        k8s_pod=getattr(args, "pod", None),
        remote_port=args.port,
    )

    started = tunnel_service.start()
    if not started:
        return None
    return tunnel_service
