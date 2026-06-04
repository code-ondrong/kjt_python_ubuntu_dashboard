# Plan: Terminal Dashboard Monitoring System (Ubuntu)

**TL;DR**: Build a real-time terminal-based system monitoring dashboard using Python `Rich` library, displaying CPU (per-core), RAM, NVIDIA GPU, HDD, top 5 CPU/RAM processes, and network I/O. Runs as a **systemd service that replaces the login prompt on tty1** — dashboard appears immediately at boot before login. Fallback login via Ctrl+Alt+F2 (tty2).

### 🏗 Phase 1: Project Scaffolding

**Steps (parallel):**
1. Create project directory structure
2. Create `requirements.txt` — `rich>=13.0.0`, `psutil>=5.9.0`
3. Create `config.py` — constants, colors, thresholds, refresh interval

### 📊 Phase 2: Data Collection *(parallel — all independent)*

**Steps (parallel):**
4. Create `system_stats.py` — all system metric functions:
   - `get_cpu_usage()` → overall %, per-core list[], frequency MHz, load average
   - `get_ram_usage()` → percent, used_gb, total_gb
   - `get_disk_usage(paths=["/"])` → [{mount, percent, used_gb, total_gb}, ...]
   - `get_network_speed()` → rx_speed, tx_speed (KB/s) — delta-based
   - `get_uptime()` → "Xh Ym" string
   - `get_system_info()` → hostname, OS/arch
   - `get_top_processes_cpu(n=5)` → [(pid, name, cpu%, mem%), ...] sorted by CPU desc
   - `get_top_processes_mem(n=5)` → [(pid, name, cpu%, mem%), ...] sorted by MEM desc
5. Create `gpu_stats.py`:
   - `get_gpu_info()` → [{index, name, util_gpu, mem_used, mem_total, temp, power}, ...]
   - Uses `subprocess.run(["nvidia-smi", "--query-gpu=...", "--format=csv,noheader,nounits"])`
   - Returns `[]` gracefully if nvidia-smi not found or error

### 🎨 Phase 3: Dashboard UI

**Step:**
6. Create `dashboard.py` — Rich layout builder:

```
┌───────────────────────────────────────────────────────────────┐
│   🖥 SYSTEM MONITOR — ubuntu-server   │ Uptime: 2h 15m       │
│   OS: Ubuntu 22.04 x86_64   │ Load: 0.5 0.8 1.2             │
├───────────────────────────────┬───────────────────────────────┤
│  CPU  ██████████████░░░ 73%  │  GPU 0: NVIDIA RTX 4090      │
│  ┌─────────────────────────┐ │  Util: ████████████░░ 80%    │
│  │C0 ██░░ 20% C4 ██████ 60│ │  Mem:  ██████░░░░ 40%  (4/10GB)│
│  │C1 ██████ 55% C5 ████ 45│ │  Temp: 72°C  Power: 250W     │
│  │C2 ████████ 75% C6 ███░ 30│ │                              │
│  │C3 ████ 42% C7 ██░  18% │ │                              │
│  └─────────────────────────┘ │                              │
│  Freq: 3.2GHz                │                              │
├───────────────────────────────┴───────────────────────────────┤
│  RAM  ███████████████████░░░░░  65%   6.5 GB / 16.0 GB       │
├───────────────────────────────┬───────────────────────────────┤
│  DISK /: ████████░░░░ 45%    │  NETWORK                      │
│  45G / 100G                  │  ↓ RX: 1.2 MB/s  ↑ TX: 340 KB/s│
│  DISK /data: ████░░░░ 22%   │                               │
│  220G / 1.0T                  │                               │
├───────────────────────────────┴───────────────────────────────┤
│ 🔥 TOP 5 CPU              │  💾 TOP 5 RAM                    │
│ PID  NAME         CPU% MEM%│  PID  NAME         CPU% MEM%    │
│ 1234 python3      25.5 12.3│  5678 mysqld       15.2 35.5    │
│ 5678 mysqld       15.2 35.5│  1234 python3      25.5 12.3    │
│ 9012 java          8.5  6.7│  3333 node          5.2  9.8    │
│ 3456 nginx         6.1  2.1│  7777 postgres      0.5  8.2    │
│ 7890 postgres      0.5  8.2│  9012 java          8.5  6.7    │
└───────────────────────────────┴───────────────────────────────┘
```

Layout uses `rich.layout.Layout` with:
- **Header**: system info + uptime + load
- **Row 1** (60/40 split): CPU panel (overall bar + per-core grid) | GPU panel
- **Row 2**: RAM panel (full width bar)
- **Row 3** (50/50 split): Disk panel (per-mount bars) | Network panel (RX/TX)
- **Footer** (50/50 split): Top 5 CPU table | Top 5 RAM table
- Color bars: 🟢 green if <50%, 🟡 yellow 50-80%, 🔴 red >80%

### 🚀 Phase 4: Main Entry Point

**Step:**
7. Create `main.py`:
   - Signal handlers: SIGTERM + SIGINT → graceful exit
   - Network speed tracker: class with `rx_before`/`tx_before` for delta calculation
   - Rich `Live(layout, screen=True, refresh_per_second=4)` loop
   - Collect all stats → `build_layout(stats)` → `live.update(layout)` → sleep(1)

### ⚙️ Phase 5: Systemd Service & TTY Integration *(depends on Phase 4)*

**Steps:**
8. Create `systemd/dashboard.service` — Full replacement on tty1:
   - Disables getty@tty1, runs dashboard directly on tty1
   - `Restart=always`, `RestartSec=3`
   - User: `dashboard` (dedicated system user)
   - With `StandardInput=tty`, `TTYPath=/dev/tty1`
9. Create `systemd/override.conf` — Alternative: agetty autologin drop-in (simpler)
10. Create `scripts/install_service.sh` — Full deployment script:
    - Create `dashboard` user
    - Copy files to `/opt/system-monitor/`
    - `pip install -r requirements.txt`
    - Install & enable systemd service
    - Disable getty@tty1, keep getty@tty2 as fallback
11. Create `scripts/uninstall_service.sh` — Rollback script

### 📖 Phase 6: Documentation

**Step:**
12. Create `README.md` — complete docs with:
    - Description + screenshot ascii
    - Prerequisites
    - Quick install guide
    - Service management commands
    - Key bindings
    - Troubleshooting FAQ
    - Uninstall guide

## 📁 File Structure

```
kjt_python_ubuntu_dashboard/
├── main.py                     # Main entry point
├── config.py                   # Configuration
├── system_stats.py             # CPU/RAM/Disk/Network/Process metrics
├── gpu_stats.py                # NVIDIA GPU via nvidia-smi
├── dashboard.py                # Rich layout builder
├── requirements.txt            # Python deps
├── README.md                   # Documentation
├── systemd/
│   ├── dashboard.service       # Full replacement systemd unit
│   └── override.conf           # agetty autologin drop-in (alt)
└── scripts/
    ├── install_service.sh      # Deploy & enable
    └── uninstall_service.sh    # Rollback
```

## ⚡ Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Library | Rich + psutil | Standard, well-maintained, excellent terminal rendering |
| GPU | subprocess + nvidia-smi | Native, always up-to-date, no extra deps |
| Layout | Rich Layout() | Responsive, auto-resizes with terminal |
| Process list | psutil.process_iter() | Lightweight, sorts by CPU%/MEM% |
| TTY approach | Dashboard replaces getty@tty1 | Dashboard visible immediately at boot |
| Fallback | getty@tty2 kept enabled | Ctrl+Alt+F2 for login if needed |
| Refresh rate | 1 second | Smooth updates, minimal CPU overhead |
| Service user | dashboard | Non-root, dedicated system user |

## ✅ Verification

1. `python main.py` locally — all metrics display: CPU/per-core, RAM, disk(s), GPU, network, top 5 CPU + top 5 RAM
2. Top 5 tables show real process data sorted correctly
3. Terminal resize — layout auto-adjusts
4. `Ctrl+C` — clean exit, no terminal artifacts
5. Install service → `reboot` → dashboard appears on tty1 **before login prompt**
6. `Ctrl+Alt+F2` — login prompt works as backup
7. Service crash → auto-restarts in 3s
8. Test with NVIDIA GPU → GPU metrics appear; without NVIDIA → GPU section hidden gracefully
9. `sudo systemctl stop dashboard` → tty1 falls back to something reasonable

## 🚫 Scope Boundaries

| Included | Excluded |
|----------|----------|
| CPU (overall + per-core bars) | Docker containers |
| RAM (bar + used/total) | CPU temperature sensors |
| Disk (multiple mount points) | Fan speeds, battery |
| NVIDIA GPU (util, mem, temp, power) | Web interface |
| Network (RX/TX speeds) | History/data storage |
| Top 5 CPU + Top 5 RAM processes | Email alerts |
| systemd auto-start on tty1 | Process management (kill) |
| Fallback login on tty2 | |

## ❓ Further Considerations (Answered)

1. **Top 5 processes**: ✅ 2 separate tables (CPU left, RAM right) with PID, Name, CPU%, MEM%
2. **Pre-login display**: ✅ dashboard.service replaces getty@tty1, fallback via getty@tty2 (Ctrl+Alt+F2)
3. **GPU**: ✅ NVIDIA via nvidia-smi, graceful degradation if absent