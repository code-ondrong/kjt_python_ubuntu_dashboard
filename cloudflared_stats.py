"""
Cloudflare Tunnel (cloudflared) status collection module.

Reports whether the tunnel is up and related information, combining several
low-privilege signals and degrading gracefully when any one is unavailable:

  * a running ``cloudflared`` process (via psutil)
  * the systemd service state (via ``systemctl is-active``)
  * the tunnel name / public hostnames from the local config file
  * the number of active edge connections from the local metrics endpoint

None of these require root; each is best-effort and skipped on failure.
"""

import json
import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

import psutil

from config import (
    CLOUDFLARED_CONFIG_PATHS,
    CLOUDFLARED_ENABLED,
    CLOUDFLARED_METRICS_URLS,
    CLOUDFLARED_PROCESS_NAME,
    CLOUDFLARED_SERVICE,
)


# ── Process ──────────────────────────────────────────────────────────────

def _process_info() -> Optional[Dict]:
    """Return ``{pid, cmdline}`` for the running cloudflared process, or None."""
    target = CLOUDFLARED_PROCESS_NAME.lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name.startswith(target):
                return {
                    "pid": proc.info["pid"],
                    "cmdline": proc.info.get("cmdline") or [],
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _tunnel_name_from_cmdline(cmdline: List[str]) -> str:
    """
    Best-effort tunnel name from a ``cloudflared tunnel run <name>`` cmdline.

    Returns an empty string for token-based / remotely-managed tunnels where
    no name is present on the command line.
    """
    if "run" not in cmdline:
        return ""
    idx = cmdline.index("run")
    for arg in cmdline[idx + 1:]:
        if not arg.startswith("-"):
            return arg
    return ""


# ── systemd ──────────────────────────────────────────────────────────────

def _systemd_state(service: str) -> Optional[str]:
    """Return the systemd ActiveState (e.g. ``active``) or None if unavailable."""
    if not shutil.which("systemctl"):
        return None
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # ``is-active`` exits non-zero for inactive/failed but still prints the state
    return result.stdout.strip() or None


# ── Config file ──────────────────────────────────────────────────────────

def _parse_config_text(text: str) -> Dict:
    """
    Extract the tunnel id/name and ingress hostnames from a config.yml body.

    Uses light regex instead of a full YAML parser to avoid an extra
    dependency; cloudflared configs are flat enough for this to be reliable.
    """
    tunnel = ""
    match = re.search(r"^\s*tunnel:\s*(\S+)", text, re.MULTILINE)
    if match:
        tunnel = match.group(1).strip().strip("\"'")

    hostnames = []
    for m in re.finditer(r"^\s*(?:-\s*)?hostname:\s*(\S+)", text, re.MULTILINE):
        host = m.group(1).strip().strip("\"'")
        if host and host not in hostnames:
            hostnames.append(host)

    return {"tunnel": tunnel, "hostnames": hostnames}


def _read_config() -> Dict:
    """Parse the first readable cloudflared config found in the known paths."""
    for path in CLOUDFLARED_CONFIG_PATHS:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return _parse_config_text(fh.read())
        except OSError:
            continue
    return {"tunnel": "", "hostnames": []}


# ── Metrics endpoint ─────────────────────────────────────────────────────

# cloudflared's version never changes while running, so parse it once and
# cache it to avoid fetching the (larger) /metrics body on every refresh.
_version_cache: Optional[str] = None


def _ready_connections(base: str) -> Optional[int]:
    """
    Number of ready edge connections from the ``/ready`` endpoint of *base*,
    or None if unreachable.

    ``/ready`` returns JSON like ``{"status":200,"readyConnections":4}``.
    """
    url = base.rstrip("/") + "/ready"
    try:
        with urlopen(url, timeout=1) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return int(data.get("readyConnections", 0))
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _cloudflared_version(base: str) -> str:
    """
    cloudflared version parsed once from the ``/metrics`` ``build_info`` gauge
    and cached. Returns an empty string if unavailable.
    """
    global _version_cache
    if _version_cache is not None:
        return _version_cache
    url = base.rstrip("/") + "/metrics"
    try:
        with urlopen(url, timeout=1) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (URLError, OSError):
        return ""
    match = re.search(r'build_info\{[^}]*version="([^"]+)"', body)
    _version_cache = match.group(1) if match else ""
    return _version_cache


def _metrics_info() -> Dict:
    """
    Return ``{"connections": int|None, "version": str}`` from the first
    reachable metrics server in ``CLOUDFLARED_METRICS_URLS``.

    Requires the tunnel to be started with ``--metrics <host:port>`` (or
    ``metrics:`` in config.yml) matching one of the configured URLs.
    """
    for base in CLOUDFLARED_METRICS_URLS:
        conns = _ready_connections(base)
        if conns is not None:
            return {"connections": conns, "version": _cloudflared_version(base)}
    return {"connections": None, "version": ""}


# ── Public API ───────────────────────────────────────────────────────────

def get_cloudflared_status() -> Dict:
    """
    Return the current Cloudflare Tunnel status.

    Result shape::

        {
            "enabled": bool,        # False when disabled in config
            "running": bool,        # process alive or service active
            "state": str,           # 'active' | 'inactive' | 'failed' | 'stopped'
            "pid": int | None,
            "tunnel": str,          # tunnel name/id, if discoverable
            "hostnames": [str],     # public hostnames from local config
            "connections": int | None,  # active edge connections, if metrics reachable
            "version": str,         # cloudflared version, if metrics reachable
        }

    When cloudflared is disabled, only ``{"enabled": False}`` is returned.
    """
    if not CLOUDFLARED_ENABLED:
        return {"enabled": False}

    proc = _process_info()
    state = _systemd_state(CLOUDFLARED_SERVICE)
    running = proc is not None or state == "active"

    result = {
        "enabled": True,
        "running": running,
        "state": state or ("running" if proc else "stopped"),
        "pid": proc["pid"] if proc else None,
        "tunnel": "",
        "hostnames": [],
        "connections": None,
        "version": "",
    }

    if not running:
        return result

    cfg = _read_config()
    result["tunnel"] = cfg.get("tunnel", "")
    result["hostnames"] = cfg.get("hostnames", [])
    if not result["tunnel"] and proc:
        result["tunnel"] = _tunnel_name_from_cmdline(proc["cmdline"])

    metrics = _metrics_info()
    result["connections"] = metrics["connections"]
    result["version"] = metrics["version"]

    return result
