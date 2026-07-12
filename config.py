"""
Configuration constants, colors, thresholds, and refresh settings
for the Terminal Dashboard Monitoring System.
"""

import os

# ── Refresh ──────────────────────────────────────────────────────────────
REFRESH_INTERVAL = 1  # seconds between updates

# ── Disk ─────────────────────────────────────────────────────────────────
DISK_PATHS = ["/"]
# Add additional mount points here, e.g.:
# DISK_PATHS = ["/", "/data", "/home"]

# ── Top Processes ────────────────────────────────────────────────────────
TOP_PROCESSES_COUNT = 5

# ── Color Thresholds (percent) ──────────────────────────────────────────
THRESHOLD_LOW = 50   # ≤ 50%  → green
THRESHOLD_MED = 80   # 51‑80% → yellow
                     # > 80%  → red

# ── Rich Theme Colors ────────────────────────────────────────────────────
COLOR_GREEN = "green"
COLOR_YELLOW = "yellow"
COLOR_RED = "red"
COLOR_CYAN = "cyan"
COLOR_MAGENTA = "magenta"
COLOR_WHITE = "white"
COLOR_DIM = "bright_black"

# ── Layout Split Ratios ─────────────────────────────────────────────────
LAYOUT_HEADER_RATIO = 3
LAYOUT_ROW1_RATIO = 14  # CPU + GPU
LAYOUT_ROW2_RATIO = 5   # RAM
LAYOUT_ROW3_RATIO = 11  # Disk + Network (Network shows IP + Cloudflare Tunnel)
LAYOUT_FOOTER_RATIO = 12  # Top 5 CPU + Top 5 RAM

LAYOUT_CPU_RATIO = 60
LAYOUT_GPU_RATIO = 40

LAYOUT_DISK_RATIO = 50
LAYOUT_NET_RATIO = 50

# ── Layout — Docker row ──────────────────────────────────────────────────
LAYOUT_DOCKER_ROW_RATIO = 10  # Height of the Docker containers panel

# ── Terminal ─────────────────────────────────────────────────────────────
TERMINAL_TITLE = "System Monitor — Ubuntu Dashboard"

# ── nvidia-smi ──────────────────────────────────────────────────────────
NVIDIA_SMI_QUERY = (
    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,"
    "temperature.gpu,power.draw"
)
NVIDIA_SMI_FORMAT = "--format=csv,noheader,nounits"

# ── nvidia-smi path ─────────────────────────────────────────────────────
NVIDIA_SMI_PATH = "/usr/bin/nvidia-smi"
if os.name == "nt":
    NVIDIA_SMI_PATH = "nvidia-smi"

# ── Cloudflare Tunnel (cloudflared) ──────────────────────────────────────
CLOUDFLARED_ENABLED = True          # set False to hide the tunnel section
CLOUDFLARED_SERVICE = "cloudflared"  # systemd unit name to query
CLOUDFLARED_PROCESS_NAME = "cloudflared"  # process name to look for

# Config files searched (first readable one wins) for tunnel name/hostnames.
CLOUDFLARED_CONFIG_PATHS = [
    "/etc/cloudflared/config.yml",
    os.path.expanduser("~/.cloudflared/config.yml"),
    "/root/.cloudflared/config.yml",
]

# cloudflared metrics server base URLs probed for the /ready endpoint to read
# live connection counts. Start the tunnel with `--metrics 127.0.0.1:2000`
# (or `metrics: 127.0.0.1:2000` in config.yml) so one of these matches.
CLOUDFLARED_METRICS_URLS = [
    "http://127.0.0.1:2000",
    "http://127.0.0.1:20241",
]
