"""
System statistics collection module.

Provides functions to gather CPU, RAM, disk, network, uptime,
system info, and top processes using psutil.
"""

import os
import time
from typing import Dict, List, Optional, Tuple

import psutil

from config import DISK_PATHS, TOP_PROCESSES_COUNT


# ── Helpers ──────────────────────────────────────────────────────────────

def _gb(bytes_: int) -> float:
    """Convert bytes to gigabytes, rounded to 1 decimal place."""
    return round(bytes_ / (1024 ** 3), 1)


def _kb(bytes_: int) -> float:
    """Convert bytes to kilobytes."""
    return round(bytes_ / 1024, 1)


# ── CPU ──────────────────────────────────────────────────────────────────

def get_cpu_usage() -> Dict:
    """Return CPU metrics as a dict."""
    per_core = psutil.cpu_percent(percpu=True)
    overall = psutil.cpu_percent()
    freq = psutil.cpu_freq()
    freq_mhz = round(freq.current) if freq else 0
    load_avg = [round(x, 1) for x in os.getloadavg()]
    return {
        "overall": overall,
        "per_core": per_core,
        "frequency_mhz": freq_mhz,
        "load_avg": load_avg,
        "core_count": len(per_core),
    }


# ── RAM ──────────────────────────────────────────────────────────────────

def get_ram_usage() -> Dict:
    """Return RAM metrics as a dict."""
    mem = psutil.virtual_memory()
    return {
        "percent": mem.percent,
        "used_gb": _gb(mem.used),
        "total_gb": _gb(mem.total),
    }


# ── Disk ─────────────────────────────────────────────────────────────────

def get_disk_usage(paths: Optional[List[str]] = None) -> List[Dict]:
    """Return disk usage for each mount point in *paths*."""
    if paths is None:
        paths = DISK_PATHS
    results = []
    for path in paths:
        try:
            usage = psutil.disk_usage(path)
            results.append({
                "mount": path,
                "percent": usage.percent,
                "used_gb": _gb(usage.used),
                "total_gb": _gb(usage.total),
            })
        except PermissionError:
            results.append({
                "mount": path,
                "percent": 0.0,
                "used_gb": 0.0,
                "total_gb": 0.0,
                "error": "Permission denied",
            })
    return results


# ── Network ──────────────────────────────────────────────────────────────

class NetworkSpeedTracker:
    """Tracks RX/TX speeds by comparing byte counters across intervals."""

    def __init__(self) -> None:
        self.rx_before: int = 0
        self.tx_before: int = 0
        self._sample()

    def _sample(self) -> Tuple[int, int]:
        counters = psutil.net_io_counters()
        self.rx_before = counters.bytes_recv
        self.tx_before = counters.bytes_sent
        return self.rx_before, self.tx_before

    def get_speed(self) -> Dict[str, float]:
        """Return rx_speed / tx_speed in KB/s since last call."""
        counters = psutil.net_io_counters()
        rx_now, tx_now = counters.bytes_recv, counters.bytes_sent
        rx_speed = (rx_now - self.rx_before) / 1024
        tx_speed = (tx_now - self.tx_before) / 1024
        self.rx_before = rx_now
        self.tx_before = tx_now
        return {
            "rx_speed_kbs": round(rx_speed, 1),
            "tx_speed_kbs": round(tx_speed, 1),
        }


# Keep a module-level singleton so the same tracker is reused.
_net_tracker: Optional[NetworkSpeedTracker] = None


def get_network_speed() -> Dict[str, float]:
    """Return current RX/TX speeds in KB/s (convenience wrapper)."""
    global _net_tracker
    if _net_tracker is None:
        _net_tracker = NetworkSpeedTracker()
        # First call will return 0; callers should treat 0 as "initialising"
    return _net_tracker.get_speed()


# ── CPU Temperature ─────────────────────────────────────────────────────

def get_cpu_temperature() -> Dict:
    """
    Return CPU/core temperature(s) in °C.

    Reads from ``psutil.sensors_temperatures()`` which on Linux uses
    ``/sys/class/thermal/`` and ``/sys/class/hwmon/``.

    Returns::

        {
            "available": True | False,
            "readings": [  # list of per-sensor readings
                {"label": str, "current": float, "high": float | None, "critical": float | None},
                ...
            ],
            "max": float,   # highest current temp among all sensors
        }
    """
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError):
        return {"available": False, "readings": [], "max": 0.0}

    if not temps:
        return {"available": False, "readings": [], "max": 0.0}

    readings = []
    for sensor_name, entries in temps.items():
        for entry in entries:
            readings.append({
                "label": entry.label or sensor_name,
                "current": entry.current,
                "high": entry.high,
                "critical": entry.critical,
            })

    max_temp = max(r["current"] for r in readings) if readings else 0.0
    return {"available": True, "readings": readings, "max": max_temp}


# ── Uptime ───────────────────────────────────────────────────────────────

def get_uptime() -> str:
    """Return human-readable uptime string, e.g. '2h 15m'."""
    uptime_seconds = time.time() - psutil.boot_time()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# ── System Info ──────────────────────────────────────────────────────────

def get_system_info() -> Dict[str, str]:
    """Return hostname and OS / architecture string."""
    import platform
    return {
        "hostname": platform.node(),
        "os_arch": f"{platform.system()} {platform.machine()}",
    }


# ── Top Processes ────────────────────────────────────────────────────────

def _process_sort_key(proc, attr: str):
    """Return sort key for a psutil.Process, defaulting to 0 on error."""
    try:
        return getattr(proc, attr)()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


def get_top_processes(sort_by: str = "cpu", n: int = TOP_PROCESSES_COUNT) -> List[Dict]:
    """
    Return top *n* processes sorted by *sort_by*.

    Supported sort keys: ``"cpu"`` (default), ``"memory"``, ``"pid"``, ``"name"``.
    """
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            pinfo = proc.info
            pid = pinfo["pid"]
            name = pinfo["name"] or ""
            cpu = pinfo["cpu_percent"] or 0.0
            mem = pinfo["memory_percent"] or 0.0
            processes.append({
                "pid": pid,
                "name": name,
                "cpu_percent": round(cpu, 1),
                "mem_percent": round(mem, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    sort_key = sort_by.lower()
    if sort_key == "memory" or sort_key == "mem":
        key_func = lambda p: p["mem_percent"]
        reverse = True
    elif sort_key == "pid":
        key_func = lambda p: p["pid"]
        reverse = True  # highest PID first
    elif sort_key == "name":
        key_func = lambda p: p["name"].lower()
        reverse = False  # A-Z
    else:  # default: cpu
        key_func = lambda p: p["cpu_percent"]
        reverse = True

    processes.sort(key=key_func, reverse=reverse)
    return processes[:n]


def get_top_processes_cpu(n: int = TOP_PROCESSES_COUNT) -> List[Dict]:
    """Return top *n* processes by CPU usage."""
    return get_top_processes(sort_by="cpu", n=n)


def get_top_processes_mem(n: int = TOP_PROCESSES_COUNT) -> List[Dict]:
    """Return top *n* processes by memory usage."""
    return get_top_processes(sort_by="memory", n=n)
