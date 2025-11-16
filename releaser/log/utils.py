#!/usr/bin/env python3
"""
Utility functions for system resource detection and parsing.

This module provides utilities for:
- Memory size parsing (e.g., "16GB" -> bytes)
- CPU limit detection from cgroups
- Memory limit detection from cgroups
- GPU resource detection via nvidia-smi
- System resource information gathering
"""

import argparse
import re
import subprocess
from typing import Any, Dict, Optional, Union

try:
    import psutil  # type: ignore[import-untyped]
except ImportError:
    psutil = None


def parse_memory_size(value: Union[str, int, float, None]) -> Optional[int]:
    """
    Parse memory strings to bytes.

    Args:
        value: Memory value as string (e.g., "16GB", "512M") or number

    Returns:
        Memory in bytes or None if invalid

    Examples:
        "16GB" -> 17179869184
        "512M" -> 536870912
        1024 -> 1024
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    value_str = str(value).strip().upper().replace("BPS", "B")

    # Match patterns like "16GB", "512M", "1024"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGTP]?B?)", value_str)
    if not match:
        try:
            return int(float(value_str))
        except (ValueError, TypeError):
            return None

    number = float(match.group(1))
    unit = match.group(2) or "B"
    if unit and not unit.endswith("B"):
        unit += "B"

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        "PB": 1024**5,
    }
    return int(number * multipliers.get(unit, 1))


def _read_cgroup_value(path: str) -> Optional[int]:
    """Read integer value from cgroup file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.lower() == "max":
                return None
            return int(content)
    except (OSError, ValueError):
        return None


def detect_cpu_limit() -> Optional[float]:
    """Detect CPU limit from cgroups or system."""
    # Try cgroup v2 first
    try:
        with open("/sys/fs/cgroup/cpu.max", "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
            if len(parts) >= 2 and parts[0] != "max":
                quota = float(parts[0])
                period = float(parts[1])
                if period > 0:
                    return max(1.0, quota / period)
    except (OSError, ValueError, IndexError):
        pass

    # Try cgroup v1
    quota = _read_cgroup_value("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read_cgroup_value("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and quota > 0 and period > 0:
        return max(1.0, float(quota) / float(period))

    # Fallback to system CPU count
    if psutil:
        try:
            return float(psutil.cpu_count(logical=True))
        except Exception:
            pass
    return None


def detect_memory_limit() -> Optional[int]:
    """Detect memory limit from cgroups or system."""
    # Try cgroup v2
    memory_limit = _read_cgroup_value("/sys/fs/cgroup/memory.max")
    if memory_limit is None:
        # Try cgroup v1
        memory_limit = _read_cgroup_value("/sys/fs/cgroup/memory/memory.limit_in_bytes")

    # Get system total memory as fallback/validation
    system_memory = None
    if psutil:
        try:
            system_memory = int(psutil.virtual_memory().total)
        except Exception:
            pass

    if memory_limit and system_memory:
        # Some systems show very large number when unlimited
        if memory_limit <= 0 or memory_limit > system_memory * 10:
            return system_memory
        return memory_limit

    return memory_limit or system_memory


def detect_gpu_resources() -> tuple[Optional[int], Optional[int]]:
    """
    Detect GPU count and total VRAM using nvidia-smi.

    Returns:
        Tuple of (gpu_count, total_vram_bytes)
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None, None

        memory_lines = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]
        if not memory_lines:
            return None, None

        # Convert MB to bytes
        gpu_memory_mb = [int(mem) for mem in memory_lines]
        total_vram = sum(gpu_memory_mb) * 1024 * 1024

        return len(gpu_memory_mb), total_vram

    except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, OSError):
        return None, None


def get_system_resources(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Get system resource limits from arguments or auto-detection.

    Args:
        args: Command line arguments

    Returns:
        Dictionary with resource information
    """
    # Use provided values or auto-detect
    cpu_cores = getattr(args, "max_cpu_cores", None)
    if cpu_cores is None:
        cpu_cores = detect_cpu_limit()

    memory_bytes = parse_memory_size(getattr(args, "max_memory", None))
    if memory_bytes is None:
        memory_bytes = detect_memory_limit()

    gpu_count = getattr(args, "gpu_count", None)
    gpu_memory = getattr(args, "max_gpu_memory", None)

    if gpu_count is None or gpu_memory is None:
        detected_count, detected_memory = detect_gpu_resources()
        if gpu_count is None:
            gpu_count = detected_count
        if gpu_memory is None:
            gpu_memory = detected_memory

    return {
        "cpuCores": cpu_cores,
        "memoryBytes": memory_bytes,
        "gpuCount": gpu_count,
        "gpuMemoryBytes": gpu_memory,
    }
