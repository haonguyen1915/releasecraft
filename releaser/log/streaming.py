#!/usr/bin/env python3
"""
Core log streaming functionality.

This module provides the main streaming classes:
- LogStreamingClient: Socket.IO client for streaming logs to a central server
- LogStreamer: Context manager wrapper for easier usage
"""

import asyncio
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import socketio  # type: ignore[import-untyped]

from ..console import console, logger
from .capture import KubernetesEventsCapture, KubernetesLogCapture, OutputCapture

try:
    import psutil  # type: ignore[import-untyped]
except ImportError:
    psutil = None

# Configure logging
logging.basicConfig(level=logging.WARNING)
module_logger = logging.getLogger(__name__)


class LogStreamingClient:
    """Socket.IO client for streaming logs to a central server."""

    def __init__(
        self,
        server_url: str,
        service_name: Optional[str],
        auth_token: str,
        echo_enabled: bool = True,
        server_name: Optional[str] = None,
        server_info: Optional[Dict] = None,
    ):
        self.server_url = self._normalize_server_url(server_url)
        self.service_name = service_name or "unknown-service"
        self.auth_token = auth_token
        self.echo_enabled = echo_enabled
        self.log_queue: queue.Queue = queue.Queue()
        self.is_running = False
        self.socket_client: Optional[socketio.AsyncClient] = None
        self.original_stdout = None
        self.original_stderr = None
        self.kubectl_capture = KubernetesLogCapture(self.log_queue, echo_enabled)
        self.server_name = server_name or f"server-{int(time.time() * 1000)}"
        self.server_info = server_info or {}
        self._registration_complete = asyncio.Event()
        self.public_tunnel_info: Optional[Dict] = None
        self.k8s_events_capture = KubernetesEventsCapture(self.log_queue, echo_enabled)

    @staticmethod
    def _normalize_server_url(url: str) -> str:
        """Normalize server URL from legacy WebSocket format to HTTP."""
        url = url.strip()

        # Convert WebSocket URLs to HTTP
        if url.startswith("ws://"):
            url = "http://" + url[5:]
        elif url.startswith("wss://"):
            url = "https://" + url[6:]

        # Remove legacy WebSocket paths
        for suffix in ("/ws/client", "/ws/ui"):
            if url.endswith(suffix):
                url = url[: -len(suffix)]
                break

        return url.rstrip("/")

    async def connect(self) -> bool:
        """Connect to the Socket.IO server and register this client."""
        try:
            self.socket_client = socketio.AsyncClient(reconnection=True)

            @self.socket_client.event
            async def connect():
                console.print("✓ [green]Connected to log server[/green]")
                # Register this client
                await self.socket_client.emit(
                    "server_registration",
                    {
                        "clientId": f"client-{int(time.time() * 1000)}",
                        "serviceName": self.service_name,
                        "serverName": self.server_name,
                        "serverInfo": self.server_info,
                    },
                )

            @self.socket_client.on("registration_ack")
            async def on_registration_ack(data):
                server_name = data.get("serverName") or self.server_name
                console.print(f"✓ [green]Registered as server: {server_name}[/green]")
                self._registration_complete.set()

            # Control channel to remotely manage the client from UI/backend
            @self.socket_client.on("control")
            async def on_control(data):
                try:
                    action = str(data.get("action", "")).lower()
                    target_service = data.get("serviceName")
                    if action in ("stop", "stop_service", "shutdown") and (
                        not target_service or target_service == self.service_name
                    ):
                        console.print(
                            "⚠️ [green]Received remote stop command; sending SIGINT...[/green]"
                        )
                        await self._exit_process_gracefully()
                except Exception:
                    pass

            @self.socket_client.on("stop_service")
            async def on_stop_service(data=None):
                try:
                    # Optional service targeting support
                    target_service = (
                        (data or {}).get("serviceName")
                        if isinstance(data, dict)
                        else None
                    )
                    if not target_service or target_service == self.service_name:
                        console.print(
                            "⚠️ [green]Received stop_service event; sending SIGINT...[/green]"
                        )
                        await self._exit_process_gracefully()
                except Exception:
                    pass

            @self.socket_client.event
            async def disconnect():
                console.print("[yellow]Disconnected from log server[/yellow]")

            # Connect with authentication token
            connect_url = f"{self.server_url}?token={self.auth_token}"
            await self.socket_client.connect(
                connect_url,
                headers={"Authorization": f"Bearer {self.auth_token}"},
                wait=True,
            )

            # Wait for registration acknowledgment
            try:
                await asyncio.wait_for(self._registration_complete.wait(), timeout=3)
            except asyncio.TimeoutExpired:
                pass

            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    async def stream_logs(self) -> None:
        """Stream logs from queue to server and send periodic resource updates."""
        last_resource_update = 0.0
        last_network_stats = None

        while self.is_running:
            try:
                # Process queued logs
                logs_to_send = []
                deadline = asyncio.get_event_loop().time() + 0.1

                while asyncio.get_event_loop().time() < deadline:
                    try:
                        log_entry = self.log_queue.get_nowait()
                        logs_to_send.append(log_entry)
                    except queue.Empty:
                        break

                # Send logs to server
                if self.socket_client and self.socket_client.connected:
                    for log_entry in logs_to_send:
                        if log_entry.get("type") == "log":
                            await self._send_log_entry(log_entry)

                await asyncio.sleep(0.1)

                # Send resource updates every 2 seconds
                current_time = time.time()
                if (
                    self.socket_client
                    and self.socket_client.connected
                    and current_time - last_resource_update >= 2.0
                ):
                    last_resource_update = current_time
                    resource_data = self._collect_resource_data(
                        current_time, last_network_stats
                    )

                    if "network" in resource_data:
                        last_network_stats = resource_data["_last_network_stats"]
                        del resource_data["_last_network_stats"]

                    await self._send_resource_update(resource_data)

            except Exception as e:
                module_logger.error(f"Error in log streaming loop: {e}")
                await asyncio.sleep(1)

    async def _send_log_entry(self, log_entry: Dict) -> None:
        """Send a single log entry to the server."""
        payload = {
            "level": log_entry.get("level", "INFO"),
            "service": self.service_name,
            "message": log_entry.get("message", ""),
            "source": log_entry.get("source", "local"),
            "serverName": self.server_name,
        }
        try:
            await self.socket_client.emit("log_entry", payload)
        except Exception:
            pass

    def _collect_resource_data(self, current_time: float, last_network_stats) -> Dict:
        """Collect current resource usage data."""
        resource_data = {}

        if psutil:
            try:
                # CPU usage
                resource_data["cpuPercent"] = psutil.cpu_percent(interval=None)

                # Memory usage
                memory = psutil.virtual_memory()
                resource_data["memoryBytes"] = int(memory.used)

                # Network statistics
                network_io = psutil.net_io_counters()
                if last_network_stats is None:
                    last_network_stats = (
                        network_io.bytes_recv,
                        network_io.bytes_sent,
                        current_time,
                    )
                else:
                    prev_recv, prev_sent, prev_time = last_network_stats
                    time_delta = max(0.001, current_time - prev_time)

                    rx_rate = (network_io.bytes_recv - prev_recv) / time_delta
                    tx_rate = (network_io.bytes_sent - prev_sent) / time_delta

                    resource_data["network"] = {
                        "rxBytesPerSec": rx_rate,
                        "txBytesPerSec": tx_rate,
                        "totalRxBytes": network_io.bytes_recv,
                        "totalTxBytes": network_io.bytes_sent,
                    }
                    resource_data["_last_network_stats"] = (
                        network_io.bytes_recv,
                        network_io.bytes_sent,
                        current_time,
                    )

            except Exception as e:
                module_logger.debug(f"Error collecting resource data: {e}")

        # Include public tunnel info if available
        if self.public_tunnel_info:
            try:
                resource_data["publicTunnel"] = dict(self.public_tunnel_info)
            except Exception:
                resource_data["publicTunnel"] = self.public_tunnel_info

        return resource_data

    async def _send_resource_update(self, resource_data: Dict) -> None:
        """Send resource update to server."""
        try:
            await self.socket_client.emit(
                "resource_update",
                {
                    "serverName": self.server_name,
                    "current": resource_data,
                },
            )
        except Exception:
            pass

    def start_output_capture(self) -> None:
        """Start capturing stdout and stderr."""
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        sys.stdout = OutputCapture(
            "stdout", self.original_stdout, self.log_queue, self.echo_enabled
        )
        sys.stderr = OutputCapture(
            "stderr", self.original_stderr, self.log_queue, self.echo_enabled
        )

    def stop_output_capture(self) -> None:
        """Restore original stdout and stderr."""
        if self.original_stdout:
            sys.stdout = self.original_stdout
        if self.original_stderr:
            sys.stderr = self.original_stderr

    def start_k8s_events(
        self, types: Optional[List[str]] = None, all_namespaces: bool = True
    ) -> bool:
        """Begin streaming Kubernetes Warning events to server."""
        return self.k8s_events_capture.start_capture(
            types=types, all_namespaces=all_namespaces
        )

    def stop_k8s_events(self) -> None:
        """Stop streaming Kubernetes events."""
        self.k8s_events_capture.stop_capture()

    async def run(self) -> None:
        """Main execution loop."""
        self.is_running = True

        # Connect to server
        if not await self.connect():
            return

        # Start capturing output
        self.start_output_capture()

        try:
            # Stream logs until stopped
            await self.stream_logs()
        finally:
            # Cleanup
            self.stop_output_capture()
            self.kubectl_capture.stop_capture()
            self.k8s_events_capture.stop_capture()
            if self.socket_client and self.socket_client.connected:
                await self.socket_client.disconnect()

    def stop(self) -> None:
        """Stop the streaming client."""
        self.is_running = False
        self.kubectl_capture.stop_capture()
        self.k8s_events_capture.stop_capture()

    async def _exit_process_gracefully(self) -> None:
        """Attempt to terminate this process like Ctrl+C (SIGINT), then exit(0) fallback."""
        try:
            # Prefer raising SIGINT so any handlers can perform cleanup
            try:
                signal.raise_signal(signal.SIGINT)
            except Exception:
                try:
                    os.kill(os.getpid(), signal.SIGINT)
                except Exception:
                    pass
        except Exception:
            pass
        # Small delay to allow handlers to run; then ensure termination
        try:
            await asyncio.sleep(0.1)
        except Exception:
            pass
        try:
            # Graceful exit if still running
            import sys as _sys

            _sys.exit(0)
        except Exception:
            pass
        # Hard exit fallback
        os._exit(0)


class LogStreamer:
    """Context manager for log streaming."""

    def __init__(
        self,
        server_url: str = "ws://localhost:8000/ws/client",
        service_name: Optional[str] = None,
        auth_token: str = "secret-token-change-me",
        echo_enabled: bool = True,
        server_name: Optional[str] = None,
        server_info: Optional[Dict] = None,
    ):
        self.client = LogStreamingClient(
            server_url, service_name, auth_token, echo_enabled, server_name, server_info
        )
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.background_thread: Optional[threading.Thread] = None

    def __enter__(self):
        """Start log streaming."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop log streaming."""
        self.stop()

    def start(self) -> None:
        """Start the log streaming in a background thread."""

        def run_event_loop():
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)
            try:
                self.event_loop.run_until_complete(self.client.run())
            finally:
                # Ensure pending tasks are allowed to settle, then close the loop
                try:
                    pending = asyncio.all_tasks(loop=self.event_loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        self.event_loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except Exception:
                    pass
                try:
                    self.event_loop.run_until_complete(asyncio.sleep(0))
                except Exception:
                    pass
                try:
                    self.event_loop.close()
                except Exception:
                    pass

        self.background_thread = threading.Thread(target=run_event_loop, daemon=True)
        self.background_thread.start()

        # Allow time for connection
        time.sleep(1)

    def stop(self) -> None:
        """Stop the log streaming."""
        if self.client:
            self.client.stop()

        if self.background_thread:
            self.background_thread.join(timeout=5)
            if self.background_thread.is_alive() and self.event_loop:
                # Fallback: request loop stop and wait briefly
                try:
                    self.event_loop.call_soon_threadsafe(self.event_loop.stop)
                except Exception:
                    pass
                self.background_thread.join(timeout=2)

    def log(self, message: str, level: str = "INFO") -> None:
        """Manually send a log message."""
        self.client.log_queue.put(
            {
                "type": "log",
                "level": level,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def capture_subprocess_output(self, process: subprocess.Popen) -> None:
        """Capture output from a subprocess."""

        def capture_stream(stream, log_level):
            for line in iter(stream.readline, b""):
                if line:
                    decoded_line = line.decode("utf-8", errors="replace").rstrip("\n")
                    self.log(decoded_line, log_level)

        if process.stdout:
            threading.Thread(
                target=capture_stream, args=(process.stdout, "INFO"), daemon=True
            ).start()
        if process.stderr:
            threading.Thread(
                target=capture_stream, args=(process.stderr, "ERROR"), daemon=True
            ).start()

    def start_kubectl_logs(
        self,
        namespace: Optional[str],
        pod_name: str,
        container: Optional[str] = None,
        follow: bool = True,
        tail_lines: Optional[int] = None,
        since: Optional[str] = None,
    ) -> bool:
        """Start capturing kubectl logs."""
        return self.client.kubectl_capture.start_capture(
            namespace, pod_name, container, follow, tail_lines, since
        )

    def stop_kubectl_logs(self) -> None:
        """Stop capturing kubectl logs."""
        self.client.kubectl_capture.stop_capture()

    def list_pods(self, namespace: Optional[str] = None) -> List[str]:
        """Get list of pods."""
        return self.client.kubectl_capture.list_pods(namespace)

    def list_namespaces(self) -> List[str]:
        """Get list of namespaces."""
        return self.client.kubectl_capture.list_namespaces()

    def start_k8s_events(
        self, types: Optional[List[str]] = None, all_namespaces: bool = True
    ) -> bool:
        """Start streaming Kubernetes events (Warning) across namespaces."""
        return self.client.start_k8s_events(types=types, all_namespaces=all_namespaces)

    def stop_k8s_events(self) -> None:
        """Stop streaming Kubernetes events."""
        self.client.stop_k8s_events()
