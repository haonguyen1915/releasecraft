#!/usr/bin/env python3
"""
Output capture classes for different log sources.

This module provides classes for capturing output from:
- stdout/stderr streams 
- kubectl logs from Kubernetes pods
- kubectl events from Kubernetes clusters
"""

import io
import logging
import queue
import shutil
import subprocess
import threading
from datetime import datetime
from typing import List, Optional

from ..console import console, error_console

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class OutputCapture:
    """Captures stdout/stderr and forwards to a queue for streaming."""

    def __init__(
        self,
        stream_name: str,
        original_stream,
        log_queue: queue.Queue,
        echo_enabled: bool = True,
    ):
        self.stream_name = stream_name
        self.original_stream = original_stream
        self.log_queue = log_queue
        self.echo_enabled = echo_enabled

    def write(self, text: str) -> None:
        if text:
            # Queue log entry for streaming
            self.log_queue.put(
                {
                    "type": "log",
                    "level": "ERROR" if self.stream_name == "stderr" else "INFO",
                    "message": text.rstrip("\n"),
                    "timestamp": datetime.now().isoformat(),
                }
            )

        # Echo to original stream if enabled
        if self.echo_enabled and self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()

    def flush(self) -> None:
        if self.original_stream:
            self.original_stream.flush()

    def fileno(self) -> int:
        if self.original_stream:
            return self.original_stream.fileno()
        raise io.UnsupportedOperation("fileno")

    def isatty(self) -> bool:
        if self.original_stream:
            return self.original_stream.isatty()
        return False


class KubernetesLogCapture:
    """Captures kubectl logs and forwards to a queue."""

    def __init__(self, log_queue: queue.Queue, echo_enabled: bool = True):
        self.log_queue = log_queue
        self.echo_enabled = echo_enabled
        self.is_running = False
        self.process: Optional[subprocess.Popen] = None
        self.capture_thread: Optional[threading.Thread] = None

    def start_capture(
        self,
        namespace: Optional[str],
        pod_name: str,
        container: Optional[str] = None,
        follow: bool = True,
        tail_lines: Optional[int] = None,
        since: Optional[str] = None,
    ) -> bool:
        """
        Start capturing kubectl logs for a specific pod.

        Args:
            namespace: Kubernetes namespace
            pod_name: Name of the pod
            container: Container name (optional)
            follow: Whether to follow log stream
            tail_lines: Number of lines to tail
            since: Show logs since timestamp

        Returns:
            True if capture started successfully
        """
        if self.is_running:
            self.stop_capture()

        self.is_running = True

        # Build kubectl command
        cmd = ["kubectl", "logs"]

        if namespace:
            cmd.extend(["--namespace", namespace])
        if container:
            cmd.extend(["--container", container])
        if follow:
            cmd.append("--follow")
        if tail_lines:
            cmd.extend(["--tail", str(tail_lines)])
        if since:
            cmd.extend(["--since", since])

        cmd.append(pod_name)

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            self.capture_thread = threading.Thread(
                target=self._capture_output, daemon=True
            )
            self.capture_thread.start()
            return True

        except Exception as e:
            logger.error(f"Failed to start kubectl logs: {e}")
            return False

    def _capture_output(self) -> None:
        """Capture output from kubectl process."""
        if not self.process:
            return

        try:
            # Capture stdout
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ""):
                    if not self.is_running:
                        break
                    if line.strip():
                        self._queue_log_line(f"[kubectl] {line.rstrip()}", "INFO")

            # Capture stderr
            if self.process.stderr:
                for line in iter(self.process.stderr.readline, ""):
                    if not self.is_running:
                        break
                    if line.strip():
                        self._queue_log_line(f"[kubectl] {line.rstrip()}", "ERROR")

        except Exception as e:
            logger.error(f"Error capturing kubectl output: {e}")

    def _queue_log_line(self, message: str, level: str) -> None:
        """Queue a log line for streaming."""
        self.log_queue.put(
            {
                "type": "log",
                "level": level,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

        if self.echo_enabled:
            if level == "ERROR":
                error_console.print(f"{message}")
            else:
                console.print(f"{message}")

    def stop_capture(self) -> None:
        """Stop capturing kubectl logs."""
        self.is_running = False

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.error(f"Error stopping kubectl process: {e}")

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)

    def list_pods(self, namespace: Optional[str] = None) -> List[str]:
        """Get list of pods using kubectl."""
        try:
            cmd = [
                "kubectl",
                "get",
                "pods",
                "--no-headers",
                "--output",
                "custom-columns=NAME:.metadata.name",
            ]
            if namespace:
                cmd.extend(["--namespace", namespace])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return [pod.strip() for pod in result.stdout.split("\n") if pod.strip()]
            else:
                logger.error(f"Failed to get pods: {result.stderr}")
                return []

        except Exception as e:
            logger.error(f"Error getting pods: {e}")
            return []

    def list_namespaces(self) -> List[str]:
        """Get list of namespaces."""
        try:
            cmd = [
                "kubectl",
                "get",
                "namespaces",
                "--no-headers",
                "--output",
                "custom-columns=NAME:.metadata.name",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return [ns.strip() for ns in result.stdout.split("\n") if ns.strip()]
            else:
                logger.error(f"Failed to get namespaces: {result.stderr}")
                return []

        except Exception as e:
            logger.error(f"Error getting namespaces: {e}")
            return []


class KubernetesEventsCapture:
    """Captures kubectl events (Warning) across namespaces and forwards to a queue."""

    def __init__(self, log_queue: queue.Queue, echo_enabled: bool = True):
        self.log_queue = log_queue
        self.echo_enabled = echo_enabled
        self.is_running = False
        self.process: Optional[subprocess.Popen] = None
        self.capture_thread: Optional[threading.Thread] = None

    def start_capture(
        self, types: Optional[List[str]] = None, all_namespaces: bool = True
    ) -> bool:
        """Start capturing kubernetes events. Defaults to Warning types across all namespaces."""
        if shutil.which("kubectl") is None:
            logger.error("kubectl not found; cannot capture events")
            return False

        if self.is_running:
            self.stop_capture()
        self.is_running = True

        event_types = types or ["Warning"]

        # Prefer 'kubectl events' if available; fallback to 'kubectl get events'
        preferred_cmd = ["kubectl", "events", "--watch"]
        for t in event_types:
            preferred_cmd.extend(["--types", t])
        if all_namespaces:
            preferred_cmd.append("-A")

        fallback_cmd = ["kubectl", "get", "events", "--watch-only"]
        if all_namespaces:
            fallback_cmd.append("--all-namespaces")
        if event_types:
            # type=Warning, or comma separated if multiple
            selector = ",".join([f"type={t}" for t in event_types])
            fallback_cmd.extend(["--field-selector", selector])

        cmd_to_run = preferred_cmd
        try:
            # Quick probe to see if 'kubectl events' is supported
            probe = subprocess.run(
                ["kubectl", "events", "--help"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if probe.returncode != 0:
                cmd_to_run = fallback_cmd
        except Exception:
            cmd_to_run = fallback_cmd

        try:
            self.process = subprocess.Popen(
                cmd_to_run,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            self.capture_thread = threading.Thread(
                target=self._capture_output, daemon=True
            )
            self.capture_thread.start()
            return True

        except Exception as e:
            logger.error(f"Failed to start kubectl events: {e}")
            return False

    def _queue_event_line(self, message: str, level: str = "WARNING") -> None:
        self.log_queue.put(
            {
                "type": "log",
                "level": level,
                "message": f"[k8s-event] {message}",
                "source": "k8s",
                "timestamp": datetime.now().isoformat(),
            }
        )
        if self.echo_enabled:
            if level == "ERROR":
                error_console.print(f"[k8s-event] {message}")
            else:
                console.print(f"[k8s-event] {message}")

    def _capture_output(self) -> None:
        if not self.process:
            return
        try:
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ""):
                    if not self.is_running:
                        break
                    if line.strip():
                        self._queue_event_line(line.rstrip(), "WARNING")
            if self.process.stderr:
                for line in iter(self.process.stderr.readline, ""):
                    if not self.is_running:
                        break
                    if line.strip():
                        # Treat stderr from kubectl as ERROR level for visibility
                        self._queue_event_line(line.rstrip(), "ERROR")
        except Exception as e:
            logger.error(f"Error capturing kubectl events output: {e}")

    def stop_capture(self) -> None:
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.error(f"Error stopping kubectl events process: {e}")
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)

    def list_pods(self, namespace: Optional[str] = None) -> List[str]:
        """Get list of pods using kubectl."""
        try:
            cmd = [
                "kubectl",
                "get",
                "pods",
                "--no-headers",
                "--output",
                "custom-columns=NAME:.metadata.name",
            ]
            if namespace:
                cmd.extend(["--namespace", namespace])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return [pod.strip() for pod in result.stdout.split("\n") if pod.strip()]
            else:
                logger.error(f"Failed to get pods: {result.stderr}")
                return []

        except Exception as e:
            logger.error(f"Error getting pods: {e}")
            return []

    def list_namespaces(self) -> List[str]:
        """Get list of namespaces."""
        try:
            cmd = [
                "kubectl",
                "get",
                "namespaces",
                "--no-headers",
                "--output",
                "custom-columns=NAME:.metadata.name",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return [ns.strip() for ns in result.stdout.split("\n") if ns.strip()]
            else:
                logger.error(f"Failed to get namespaces: {result.stderr}")
                return []

        except Exception as e:
            logger.error(f"Error getting namespaces: {e}")
            return []
