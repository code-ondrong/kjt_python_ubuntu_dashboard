"""
Docker container statistics module.

Collects running container metrics via ``docker stats`` subprocess.
Gracefully returns an empty list if Docker is not available.
"""

import re
import shutil
import subprocess
from typing import Dict, List, Optional


def _docker_available() -> bool:
    """Return ``True`` if the ``docker`` command is found on the system."""
    return shutil.which("docker") is not None


def _parse_mem_usage(mem_str: str) -> float:
    """
    Parse a memory string like ``"123.4MiB / 1.952GiB"`` and return
    the used amount as a float in MiB.
    """
    if not mem_str or "/" not in mem_str:
        return 0.0
    used_part = mem_str.split("/")[0].strip()
    return _parse_mem_value(used_part)


def _parse_mem_total(mem_str: str) -> float:
    """Parse a memory string and return the total amount in MiB."""
    if not mem_str or "/" not in mem_str:
        return 0.0
    total_part = mem_str.split("/")[1].strip()
    return _parse_mem_value(total_part)


def _parse_mem_value(value_str: str) -> float:
    """Convert a value like ``123.4MiB`` or ``1.952GiB`` to MiB (float)."""
    value_str = value_str.strip()
    if not value_str:
        return 0.0
    match = re.match(r"([\d.]+)\s*([KMGTP]i?B?)", value_str)
    if not match:
        # Try plain number (bytes)
        try:
            return round(float(value_str) / (1024 * 1024), 1)
        except ValueError:
            return 0.0

    num = float(match.group(1))
    unit = match.group(2).lower()

    multipliers = {
        "kib": 1.0 / 1024,
        "kb": 1.0 / 1024,
        "mib": 1.0,
        "mb": 1.0,
        "gib": 1024.0,
        "gb": 1024.0,
        "tib": 1024.0 * 1024,
        "tb": 1024.0 * 1024,
    }

    # Normalise unit
    for key, mult in multipliers.items():
        if unit.startswith(key[:2]):
            return round(num * mult, 1)

    return round(num, 1)


def _parse_pct(value_str: str) -> float:
    """Parse a percentage string like ``"2.45%\"` and return a float."""
    if not value_str:
        return 0.0
    try:
        return float(value_str.strip().replace("%", ""))
    except ValueError:
        return 0.0


def get_container_stats() -> List[Dict]:
    """
    Return stats for all running containers.

    Each dict contains::

        {
            "name": str,
            "cpu_percent": float,
            "mem_percent": float,
            "mem_used_mib": float,
            "mem_total_mib": float,
            "net_input": str,    # e.g. "1.2kB"
            "net_output": str,   # e.g. "340B"
        }

    Returns an empty list if Docker is not installed or the command fails.
    """
    if not _docker_available():
        return []

    cmd = [
        "docker", "stats", "--no-stream",
        "--format",
        "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}|{{.NetIO}}",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    containers = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue

        name = parts[0]
        cpu_pct = _parse_pct(parts[1])
        mem_pct = _parse_pct(parts[2])
        mem_used = _parse_mem_usage(parts[3])
        mem_total = _parse_mem_total(parts[3])

        # NetIO format: "1.2kB / 340B"
        net_parts = parts[4].split("/")
        net_in = net_parts[0].strip() if len(net_parts) > 0 else ""
        net_out = net_parts[1].strip() if len(net_parts) > 1 else ""

        containers.append({
            "name": name,
            "cpu_percent": cpu_pct,
            "mem_percent": mem_pct,
            "mem_used_mib": mem_used,
            "mem_total_mib": mem_total,
            "net_input": net_in,
            "net_output": net_out,
        })

    return containers
