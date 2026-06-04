"""
Main entry point for the Terminal Dashboard Monitoring System.

Collects system stats and renders a live Rich dashboard at a configurable
refresh rate. Handles SIGTERM / SIGINT for graceful shutdown.
Supports interactive commands typed on stdin (kill processes, search, etc.).
"""

import signal
import sys
import threading
import time
from typing import Dict, Optional

from rich.live import Live
from rich.layout import Layout

from config import REFRESH_INTERVAL
from dashboard import build_layout
from gpu_stats import get_gpu_info
from system_stats import (
    get_cpu_temperature,
    get_cpu_usage,
    get_disk_usage,
    get_network_speed,
    get_ram_usage,
    get_system_info,
    get_top_processes_cpu,
    get_top_processes_mem,
    get_uptime,
    NetworkSpeedTracker,
)
from docker_stats import get_container_stats
from process_manager import kill_process, parse_command, search_processes


# ── Global state ────────────────────────────────────────────────────────
_running = True
_status_message: str = ""
_status_ttl: int = 0  # remaining refreshes to show the status
_help_shown: bool = False
_sort1: str = "cpu"   # table 1 (left) sort column
_sort2: str = "mem"   # table 2 (right) sort column
_lock = threading.Lock()


_SORT_LABELS = {"cpu": "CPU%", "mem": "MEM%", "pid": "PID", "name": "NAME"}


def _handle_signal(signum: int, _frame) -> None:
    """Set the shutdown flag on SIGTERM / SIGINT."""
    global _running
    _running = False


def _stdin_reader() -> None:
    """Background daemon thread: read lines from stdin."""
    global _running
    while _running:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            _process_command(line.strip())
        except (EOFError, OSError):
            break


def _process_command(line: str) -> None:
    """Parse and execute a user command, setting the status message."""
    global _status_message, _status_ttl, _running, _help_shown

    cmd = parse_command(line)
    if cmd is None:
        return

    action = cmd["action"]

    if action == "quit":
        with _lock:
            _running = False
        return

    if action == "kill":
        result = kill_process(cmd["pid"], cmd.get("sig"))
        _set_status(result["message"], ttl=8)
        return

    if action == "search":
        results = search_processes(cmd["name"])
        if not results:
            _set_status(f"No processes found matching '{cmd['name']}'", ttl=6)
        else:
            lines = [f"{p['pid']:>6}  {p['user']:<10}  {p['command'][:50]}" for p in results[:8]]
            msg = f"Found {len(results)} process(es) for '{cmd['name']}':\n" + "\n".join(lines)
            _set_status(msg, ttl=15)
        return

    if action == "sort":
        table = cmd["table"]
        column = cmd["column"]
        label = _SORT_LABELS.get(column, column.upper())
        with _lock:
            if table == 1:
                _sort1 = column
            else:
                _sort2 = column
        _set_status(f"Table {table} sorted by {label}", ttl=4)
        return

    if action == "status":
        _set_status(cmd.get("message", ""), ttl=6)
        if "Commands:" in cmd.get("message", ""):
            _help_shown = True
        return


def _set_status(msg: str, ttl: int = 6) -> None:
    """Set the status message with a TTL (number of refresh cycles)."""
    global _status_message, _status_ttl
    with _lock:
        _status_message = msg
        _status_ttl = ttl


def _get_status() -> str:
    """Get the current status message and decrement its TTL."""
    global _status_message, _status_ttl, _help_shown
    with _lock:
        msg = _status_message
        if _status_ttl > 0:
            _status_ttl -= 1
            if _status_ttl == 0:
                _status_message = ""
        if not msg:
            if not _help_shown:
                _help_shown = True
                return "Type h + Enter for commands  |  k <PID> to kill a process"
        return msg


def _collect_stats(net_tracker: NetworkSpeedTracker) -> Dict:
    """Collect all system metrics into a single dict."""
    global _sort1, _sort2
    with _lock:
        s1, s2 = _sort1, _sort2
    return {
        "system_info": get_system_info(),
        "uptime": get_uptime(),
        "cpu": get_cpu_usage(),
        "cpu_temperature": get_cpu_temperature(),
        "ram": get_ram_usage(),
        "disk": get_disk_usage(),
        "network": net_tracker.get_speed(),
        "gpu": get_gpu_info(),
        "docker": get_container_stats(),
        "top_cpu": get_top_processes(sort_by=s1),
        "top_mem": get_top_processes(sort_by=s2),
        "sort1": s1,
        "sort2": s2,
        "status": _get_status(),
    }


def main() -> None:
    # ── Signal handlers ──────────────────────────────────────────────
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # ── Stdin reader daemon thread ───────────────────────────────────
    reader = threading.Thread(target=_stdin_reader, daemon=True)
    reader.start()

    # ── Network tracker (delta-based) ────────────────────────────────
    net_tracker = NetworkSpeedTracker()
    time.sleep(REFRESH_INTERVAL)

    # ── Live dashboard ───────────────────────────────────────────────
    try:
        with Live(
            auto_refresh=False,
            screen=True,
        ) as live:
            while _running:
                stats = _collect_stats(net_tracker)
                layout = build_layout(stats)
                live.update(layout, refresh=True)
                time.sleep(REFRESH_INTERVAL)
    except Exception:
        sys.stderr.write("\n" * 3)
        raise


if __name__ == "__main__":
    main()
