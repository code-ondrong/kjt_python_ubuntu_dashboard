"""
GPU statistics module.

Collects NVIDIA GPU metrics via the ``nvidia-smi`` command-line tool.
Gracefully returns an empty list if ``nvidia-smi`` is not available or
encounters an error.
"""

import shutil
import subprocess
from typing import Dict, List

from config import NVIDIA_SMI_FORMAT, NVIDIA_SMI_PATH, NVIDIA_SMI_QUERY


def _nvidia_smi_available() -> bool:
    """Return ``True`` if ``nvidia-smi`` is found on the system."""
    return shutil.which(NVIDIA_SMI_PATH) is not None


def get_gpu_info() -> List[Dict]:
    """
    Query all NVIDIA GPUs and return a list of dicts.

    Each dict contains::

        {
            "index": int,
            "name": str,
            "util_gpu": float,     # GPU utilisation %
            "mem_used": float,    # MB
            "mem_total": float,   # MB
            "temp": float,        # °C
            "power": float,       # Watts
        }

    Returns an empty list if ``nvidia-smi`` is missing or the query fails.
    """
    if not _nvidia_smi_available():
        return []

    cmd = [NVIDIA_SMI_PATH, NVIDIA_SMI_QUERY, NVIDIA_SMI_FORMAT]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    gpus: List[Dict] = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(", ")]
        if len(parts) < 7:
            continue
        try:
            gpu = {
                "index": int(parts[0]),
                "name": parts[1],
                "util_gpu": _to_float(parts[2]),
                "mem_used": _to_float(parts[3]),
                "mem_total": _to_float(parts[4]),
                "temp": _to_float(parts[5]),
                "power": _to_float(parts[6]),
            }
            gpus.append(gpu)
        except (ValueError, IndexError):
            continue

    return gpus


def _to_float(value: str) -> float:
    """Convert a string to float, returning 0.0 on failure."""
    try:
        return float(value)
    except ValueError:
        return 0.0
