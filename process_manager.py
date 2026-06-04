"""
Process management module.

Provides functions to parse user commands and kill processes
by PID from the dashboard interface.
"""

import os
import signal
import subprocess
from typing import Dict, List, Optional


# ── Signal mapping ───────────────────────────────────────────────────────

_SIGNAL_MAP: Dict[str, int] = {
    "SIGTERM": signal.SIGTERM,
    "SIGKILL": signal.SIGKILL,
    "SIGHUP": signal.SIGHUP,
    "SIGINT": signal.SIGINT,
    "SIGSTOP": signal.SIGSTOP,
    "SIGCONT": signal.SIGCONT,
    "15": signal.SIGTERM,
    "9": signal.SIGKILL,
    "1": signal.SIGHUP,
    "2": signal.SIGINT,
    "19": signal.SIGSTOP,
    "18": signal.SIGCONT,
}

# Reverse map for display
_SIGNAL_NAMES = {v: k for k, v in _SIGNAL_MAP.items() if k.isalpha()}


# ── Kill process ─────────────────────────────────────────────────────────

def kill_process(pid_str: str, sig_str: Optional[str] = None) -> Dict:
    """
    Kill a process by PID string.

    Args:
        pid_str: PID as a string (e.g. ``"1234"``).
        sig_str: Optional signal name or number (e.g. ``"SIGKILL"``, ``"9"``).

    Returns:
        A dict with ``"success"`` (bool) and ``"message"`` (str).
    """
    try:
        pid = int(pid_str.strip())
    except (ValueError, AttributeError):
        return {"success": False, "message": f"Invalid PID: '{pid_str}'"}

    sig = signal.SIGTERM
    if sig_str:
        sig = _SIGNAL_MAP.get(sig_str.upper(), signal.SIGTERM)

    try:
        os.kill(pid, sig)
        sig_name = _SIGNAL_NAMES.get(sig, str(sig))
        return {"success": True, "message": f"Process {pid} killed with {sig_name}"}
    except ProcessLookupError:
        return {"success": False, "message": f"Process {pid} not found"}
    except PermissionError:
        return {"success": False, "message": f"Permission denied — try 'sudo python main.py'"}
    except OSError as e:
        return {"success": False, "message": f"Error killing {pid}: {e}"}


# ── Command parsing ──────────────────────────────────────────────────────

_HELP_TEXT = (
    "Commands:  k <PID> [signal] — kill  |  "
    "s <name> — search  |  "
    "s1 <col> / s2 <col> — sort table 1/2 by cpu|mem|pid|name  |  "
    "q — quit  |  h — help"
)


def parse_command(line: str) -> Optional[Dict]:
    """
    Parse a user command string.

    Supported commands::

        k <PID> [signal]   Kill a process by PID (default SIGTERM)
                           Signals: 9/SIGKILL, 15/SIGTERM, 1/SIGHUP, etc.
        s <name>           Search processes by name
        q / quit / exit    Quit the dashboard
        h / help           Show help text

    Returns a dict with ``"action"`` and relevant params, or ``None`` for
    empty lines.
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split()
    cmd = parts[0].lower()

    if cmd in ("k", "kill"):
        if len(parts) < 2:
            return {
                "action": "status",
                "message": "Usage: k <PID> [signal]. Example: k 1234  or  k 1234 -9",
            }
        return {
            "action": "kill",
            "pid": parts[1],
            "sig": parts[2] if len(parts) > 2 else None,
        }

    elif cmd in ("s", "search"):
        if len(parts) < 2:
            return {"action": "status", "message": "Usage: s <name> to search processes"}
        return {"action": "search", "name": " ".join(parts[1:])}

    elif cmd in ("s1", "sort1"):
        col = parts[1].lower() if len(parts) > 1 else ""
        if col not in ("cpu", "mem", "memory", "pid", "name"):
            return {"action": "status", "message": "Usage: s1 <cpu|mem|pid|name> — sort table 1"}
        if col == "memory":
            col = "mem"
        return {"action": "sort", "table": 1, "column": col}

    elif cmd in ("s2", "sort2"):
        col = parts[1].lower() if len(parts) > 1 else ""
        if col not in ("cpu", "mem", "memory", "pid", "name"):
            return {"action": "status", "message": "Usage: s2 <cpu|mem|pid|name> — sort table 2"}
        if col == "memory":
            col = "mem"
        return {"action": "sort", "table": 2, "column": col}

    elif cmd in ("q", "quit", "exit"):
        return {"action": "quit"}

    elif cmd in ("h", "help", "?"):
        return {"action": "status", "message": _HELP_TEXT}

    else:
        return {
            "action": "status",
            "message": f"Unknown command '{cmd}'. Type h for help.",
        }


# ── Process search ───────────────────────────────────────────────────────

def search_processes(name: str) -> List[Dict]:
    """
    Search for processes by name using ``ps aux`` + ``grep``.

    Returns a list of dicts with ``pid``, ``user``, ``cpu``, ``mem``,
    and ``command``.
    """
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [{"pid": 0, "name": "Error: ps not available"}]

    matches = []
    for line in result.stdout.splitlines():
        if name.lower() in line.lower():
            parts = line.split(None, 10)
            if len(parts) >= 11 and parts[10] != "grep " + name:
                matches.append({
                    "user": parts[0],
                    "pid": int(parts[1]),
                    "cpu": parts[2],
                    "mem": parts[3],
                    "command": parts[10][:60],
                })

    return matches
