#!/usr/bin/env python3
"""
Public tunnel service for exposing local services.

This module provides:
- HTTP server for log endpoints  
- Bore tunnel integration for public access
- Kubernetes port-forwarding support
"""

import http.server
import json
import re
import shutil
import socketserver
import subprocess
import sys
import threading
from typing import Callable, Dict, Optional

from ..console import console, error_console, logger


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """HTTP server that handles requests in separate threads."""

    daemon_threads = True


class PublicTunnelService:
    """
    HTTP service for accepting logs with optional Bore tunnel for public access.

    Can run a local HTTP server and/or expose an existing service via Bore tunnel.
    """

    def __init__(
        self,
        port: int,
        log_callback: Optional[Callable] = None,
        tunnel_enabled: bool = False,
        tunnel_host: str = "bore.pub",
        bore_executable: str = "bore",
        tunnel_secret: Optional[str] = None,
        stdout=None,
        stderr=None,
        start_http_server: bool = True,
        tunnel_info_callback: Optional[Callable] = None,
        enable_port_forward: bool = False,
        k8s_namespace: Optional[str] = None,
        k8s_pod: Optional[str] = None,
        remote_port: Optional[int] = None,
    ):
        self.port = port
        self.log_callback = log_callback
        self.tunnel_enabled = tunnel_enabled
        self.tunnel_host = tunnel_host
        self.bore_executable = bore_executable
        self.tunnel_secret = tunnel_secret
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.start_http_server = start_http_server
        self.tunnel_info_callback = tunnel_info_callback
        self.enable_port_forward = enable_port_forward
        self.k8s_namespace = k8s_namespace
        self.k8s_pod = k8s_pod
        self.remote_port = remote_port or port

        self._http_server: Optional[_ThreadedHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._bore_process: Optional[subprocess.Popen] = None
        self._port_forward_process: Optional[subprocess.Popen] = None

    def _create_request_handler(self):
        """Create HTTP request handler class."""
        log_callback = self.log_callback
        _stdout = self.stdout

        class LogRequestHandler(http.server.BaseHTTPRequestHandler):
            def _send_json_response(self, status_code: int, data: Dict) -> None:
                response_body = json.dumps(data).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send_json_response(200, {"status": "healthy"})
                else:
                    self._send_json_response(404, {"error": "endpoint not found"})

            def do_POST(self) -> None:
                if self.path == "/log":
                    try:
                        content_length = int(self.headers.get("Content-Length", "0"))
                        request_body = (
                            self.rfile.read(content_length)
                            if content_length > 0
                            else b""
                        )
                        log_data = json.loads(request_body.decode("utf-8") or "{}")

                        log_level = str(log_data.get("level", "INFO"))
                        log_message = str(log_data.get("message", ""))

                        if not log_message:
                            self._send_json_response(
                                400, {"error": "message is required"}
                            )
                            return

                        if log_callback:
                            log_callback(log_message, log_level)
                        self._send_json_response(200, {"status": "logged"})

                    except json.JSONDecodeError:
                        self._send_json_response(400, {"error": "invalid JSON"})
                    except Exception as e:
                        self._send_json_response(500, {"error": str(e)})
                else:
                    self._send_json_response(404, {"error": "endpoint not found"})

            def log_message(self, format_str, *args):
                try:
                    console.print(f"[green]\\[http][/green] {format_str % args}")
                except Exception:
                    console.print(f"[http] {format_str % args}")

        return LogRequestHandler

    def start(self) -> bool:
        """Start the HTTP server and/or Bore tunnel."""
        # Start HTTP server if requested
        if self.start_http_server:
            try:
                self._http_server = _ThreadedHTTPServer(
                    ("0.0.0.0", self.port), self._create_request_handler()
                )

                def serve_http():
                    console.print(
                        f"✓ [green]HTTP log service running on http://127.0.0.1:{self.port}[/green]"
                    )
                    console.print("[green]   Endpoints: GET /health, POST /log[/green]")
                    self._http_server.serve_forever(poll_interval=0.5)

                self._http_thread = threading.Thread(target=serve_http, daemon=True)
                self._http_thread.start()

            except OSError as e:
                logger.error(f"Failed to start HTTP server on port {self.port}: {e}")
                return False
        else:
            console.print(
                f"✓ [green]Exposing existing service on port {self.port}[/green]"
            )

        # Start Bore tunnel if enabled
        if self.tunnel_enabled:
            # If in k8s context, optionally start kubectl port-forward first
            if self.enable_port_forward:
                if shutil.which("kubectl") is None:
                    logger.error("kubectl not found (required for port-forward)")
                    return False
                if not self.k8s_pod:
                    logger.error("--pod is required to port-forward in k8s context")
                    return False
                if not self._start_port_forward():
                    return False
                else:
                    try:
                        pid = (
                            self._port_forward_process.pid
                            if self._port_forward_process
                            else None
                        )
                        logger.success(f"kubectl port-forward started (pid={pid})")
                    except Exception:
                        pass
            if shutil.which(self.bore_executable) is None:
                logger.error(f"Bore executable '{self.bore_executable}' not found")
                error_console.print(
                    "[red]   Install with: brew install ekzhang/bore/bore[/red]"
                )
                # Exit early if bore is required
                return False
            else:
                self._start_bore_tunnel()
                try:
                    pid = self._bore_process.pid if self._bore_process else None
                    logger.success(f"Bore tunnel started (pid={pid})")
                except Exception:
                    pass

        return True

    def _start_port_forward(self) -> bool:
        """Start kubectl port-forward from local port to pod port in k8s."""
        try:
            cmd = ["kubectl", "port-forward"]
            if self.k8s_namespace:
                cmd.extend(["-n", self.k8s_namespace])
            cmd.extend([f"pod/{self.k8s_pod}", f"{self.port}:{self.remote_port}"])

            self._port_forward_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            def monitor_pf_output():
                if (
                    not self._port_forward_process
                    or not self._port_forward_process.stdout
                ):
                    return
                for line in iter(self._port_forward_process.stdout.readline, ""):
                    if not line:
                        break
                    output_line = line.rstrip()
                    console.print(f"[cyan]\\[kubectl][/cyan] {output_line}")

            threading.Thread(target=monitor_pf_output, daemon=True).start()
            return True
        except Exception as e:
            logger.error(f"Failed to start kubectl port-forward: {e}")
            return False

    def _start_bore_tunnel(self) -> None:
        """Start the Bore tunnel process."""
        try:
            tunnel_command = [
                self.bore_executable,
                "local",
                str(self.port),
                "--to",
                self.tunnel_host,
            ]
            if self.tunnel_secret:
                tunnel_command.extend(["--secret", self.tunnel_secret])

            self._bore_process = subprocess.Popen(
                tunnel_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            def monitor_bore_output():
                if not self._bore_process or not self._bore_process.stdout:
                    return

                for line in iter(self._bore_process.stdout.readline, ""):
                    if not line:
                        break

                    output_line = line.rstrip()
                    console.print(f"[cyan]\\[bore][/cyan] {output_line}")

                    # Extract tunnel information from output
                    self._parse_tunnel_info(output_line)

            threading.Thread(target=monitor_bore_output, daemon=True).start()

        except Exception as e:
            logger.error(f"Failed to start Bore tunnel: {e}")

    def _parse_tunnel_info(self, output_line: str) -> None:
        """Parse tunnel information from Bore output."""
        try:
            tunnel_info = None

            # Look for direct URL in output
            url_match = re.search(r"(https?://\S+)", output_line)
            if url_match:
                url = url_match.group(1)
                # Extract host and port from URL
                host_port_match = re.search(r"https?://([^/:\s]+)(?::(\d+))?", url)
                if host_port_match:
                    host = host_port_match.group(1)
                    port = host_port_match.group(2)
                    tunnel_info = {
                        "url": url,
                        "provider": "bore",
                        "host": host,
                        "localPort": self.port,
                    }
                    if port:
                        tunnel_info["remotePort"] = int(port)
            else:
                # Look for "listening at HOST:PORT" pattern
                listen_match = re.search(
                    r"listening at\s+([^\s:]+):(\d+)", output_line, re.IGNORECASE
                )
                if listen_match:
                    host = listen_match.group(1)
                    port = listen_match.group(2)
                    tunnel_info = {
                        "url": f"http://{host}:{port}",
                        "provider": "bore",
                        "host": host,
                        "remotePort": int(port),
                        "localPort": self.port,
                    }

            if tunnel_info and self.tunnel_info_callback:
                # Attach process IDs for observability
                if self._bore_process and self._bore_process.pid:
                    tunnel_info["borePid"] = self._bore_process.pid
                if self._port_forward_process and self._port_forward_process.pid:
                    tunnel_info["portForwardPid"] = self._port_forward_process.pid
                self.tunnel_info_callback(tunnel_info)

        except Exception:
            pass  # Ignore parsing errors

    def stop(self) -> None:
        """Stop the HTTP server and Bore tunnel."""
        if self._http_server:
            try:
                self._http_server.shutdown()
            except Exception:
                pass

        if self._http_thread and self._http_thread.is_alive():
            self._http_thread.join(timeout=2)

        if self._bore_process:
            try:
                self._bore_process.terminate()
            except Exception:
                pass
        if self._port_forward_process:
            try:
                self._port_forward_process.terminate()
            except Exception:
                pass
