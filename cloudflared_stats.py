"""
Cloudflare Tunnel (cloudflared) status collection module.

Reports whether the tunnel is up and related information, combining several
low-privilege signals and degrading gracefully when any one is unavailable:

  * a running ``cloudflared`` process (via psutil)
  * the systemd service state (via ``systemctl is-active``)
  * the tunnel name / public hostnames from the local config file
  * the number of active edge connections from the local metrics endpoint
  * public hostnames from the Cloudflare API for token-based tunnels whose
    ingress config lives in the dashboard rather than on disk

None of these require root; each is best-effort and skipped on failure.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

import psutil

from config import (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN_ENV,
    CLOUDFLARE_TUNNEL_ID,
    CLOUDFLARED_API_ENABLED,
    CLOUDFLARED_CONFIG_PATHS,
    CLOUDFLARED_ENABLED,
    CLOUDFLARED_METRICS_URLS,
    CLOUDFLARED_PROCESS_NAME,
    CLOUDFLARED_SERVICE,
    DOTENV_PATHS,
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
    # Token-based tunnels are `... run --token <TOKEN>` with no name — never
    # mistake the token value (or any flag value) for the tunnel name.
    if any(a == "--token" or a.startswith("--token=") for a in cmdline):
        return ""
    idx = cmdline.index("run")
    skip_next = False
    for arg in cmdline[idx + 1:]:
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("-"):
            skip_next = "=" not in arg  # a bare flag likely consumes the next arg
            continue
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


# ── Cloudflare API (hostnames for token-based tunnels) ───────────────────

_CF_API = "https://api.cloudflare.com/client/v4"

# Background-refreshed hostname cache so the render loop never blocks on the
# remote API. A daemon thread updates these under the lock; readers copy out.
_api_lock = threading.Lock()
_api_hostnames: List[str] = []
_api_next_refresh: float = 0.0
_api_inflight: bool = False
_API_TTL_OK = 3600.0   # re-check hostnames hourly on success
_API_TTL_ERR = 120.0   # back off 2 min after a failed/incomplete attempt


def _read_dotenv() -> Dict[str, str]:
    """Parse the first readable ``.env`` file into a dict (best-effort)."""
    for path in DOTENV_PATHS:
        if not path or not os.path.isfile(path):
            continue
        env: Dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip().strip('"').strip("'")
        except OSError:
            continue
        return env
    return {}


def _get_secret(name: str) -> str:
    """Read *name* from the OS environment first, then any ``.env`` file."""
    if os.environ.get(name):
        return os.environ[name]
    return _read_dotenv().get(name, "")


def _decode_tunnel_token(cmdline: List[str]) -> Optional[Dict]:
    """
    Decode the ``--token`` value from a cloudflared cmdline into its account
    and tunnel IDs. The token is base64(JSON) of ``{"a":..,"t":..,"s":..}``.
    """
    token = ""
    for i, arg in enumerate(cmdline):
        if arg == "--token" and i + 1 < len(cmdline):
            token = cmdline[i + 1]
            break
        if arg.startswith("--token="):
            token = arg.split("=", 1)[1]
            break
    if not token:
        return None

    pad = "=" * (-len(token) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            data = json.loads(decoder(token + pad).decode("utf-8"))
            return {"account_id": data.get("a", ""), "tunnel_id": data.get("t", "")}
        except (ValueError, json.JSONDecodeError):
            continue
    return None


def _resolve_ids(proc: Optional[Dict]) -> Dict:
    """Return account/tunnel IDs from config overrides, else the tunnel token."""
    if CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_TUNNEL_ID:
        return {"account_id": CLOUDFLARE_ACCOUNT_ID, "tunnel_id": CLOUDFLARE_TUNNEL_ID}
    if proc:
        ids = _decode_tunnel_token(proc.get("cmdline", []))
        if ids and ids["account_id"] and ids["tunnel_id"]:
            return ids
    return {"account_id": "", "tunnel_id": ""}


def _fetch_api_hostnames(account_id: str, tunnel_id: str, api_token: str) -> List[str]:
    """Fetch ingress hostnames from the Cloudflare tunnel configuration API."""
    url = f"{_CF_API}/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"
    req = Request(url, headers={"Authorization": f"Bearer {api_token}"})
    try:
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return []

    ingress = (((data or {}).get("result") or {}).get("config") or {}).get("ingress") or []
    hostnames: List[str] = []
    for rule in ingress:
        host = (rule or {}).get("hostname")
        if host and host not in hostnames:
            hostnames.append(host)
    return hostnames


def _api_hostnames_cached(proc: Optional[Dict]) -> List[str]:
    """
    Return the cached Cloudflare API hostnames, kicking off a background
    refresh when the cache is stale. Never blocks the caller on the network.
    """
    global _api_next_refresh, _api_inflight

    now = time.time()
    with _api_lock:
        if _api_inflight or now < _api_next_refresh:
            return list(_api_hostnames)
        token = _get_secret(CLOUDFLARE_API_TOKEN_ENV)
        ids = _resolve_ids(proc)
        if not (token and ids["account_id"] and ids["tunnel_id"]):
            _api_next_refresh = now + _API_TTL_ERR  # not configured yet; retry later
            return list(_api_hostnames)
        _api_inflight = True

    def _worker() -> None:
        global _api_hostnames, _api_next_refresh, _api_inflight
        hosts = _fetch_api_hostnames(ids["account_id"], ids["tunnel_id"], token)
        with _api_lock:
            if hosts:
                _api_hostnames = hosts
                _api_next_refresh = time.time() + _API_TTL_OK
            else:
                _api_next_refresh = time.time() + _API_TTL_ERR
            _api_inflight = False

    threading.Thread(target=_worker, daemon=True).start()
    with _api_lock:
        return list(_api_hostnames)


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
            "hostnames": [str],     # public hostnames (local config or Cloudflare API)
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

    # Remotely-managed (token-based) tunnels keep their ingress config in the
    # Cloudflare dashboard, so fall back to the API when nothing is on disk.
    if not result["hostnames"] and CLOUDFLARED_API_ENABLED:
        result["hostnames"] = _api_hostnames_cached(proc)

    metrics = _metrics_info()
    result["connections"] = metrics["connections"]
    result["version"] = metrics["version"]

    return result
