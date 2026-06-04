# 🖥 Terminal Dashboard Monitoring System (Ubuntu)

A real-time terminal-based system monitoring dashboard for Ubuntu servers.
Displays CPU (per-core), RAM, NVIDIA GPU, disk usage, network I/O, and top
processes — all in a beautiful Rich-powered TUI.

## Preview

```
┌───────────────────────────────────────────────────────────────┐
│   🖥 SYSTEM MONITOR — ubuntu-server   │ Uptime: 2h 15m       │
│   OS: Ubuntu 22.04 x86_64   │ Load: 0.5 0.8 1.2             │
├───────────────────────────────┬───────────────────────────────┤
│  CPU  ██████████████░░░ 73%  │  GPU 0: NVIDIA RTX 4090      │
│  ┌─────────────────────────┐ │  Util: ████████████░░ 80%    │
│  │C0 ██░░ 20% C4 ██████ 60│ │  Mem:  ██████░░░░ 40%        │
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

## Prerequisites

- **Ubuntu** 20.04+ (or any Linux with systemd)
- **Python 3.8+**
- **pip3**
- Optional: **NVIDIA GPU** with `nvidia-smi` (GPU metrics auto-detected)

## Quick Install

### 1. Run locally (no install)

```bash
pip install -r requirements.txt
python main.py
```

Press **Ctrl+C** to exit.

### 2. Full systemd service (dashboard on tty1 at boot)

```bash
sudo bash scripts/install_service.sh
sudo reboot
```

After reboot the dashboard appears on **tty1** (Ctrl+Alt+F1) immediately.
Use **Ctrl+Alt+F2** for a regular login prompt.

## Service Management

```bash
# Status
sudo systemctl status dashboard

# View logs
sudo journalctl -u dashboard -f

# Restart
sudo systemctl restart dashboard

# Stop (tty1 falls back to login prompt)
sudo systemctl stop dashboard

# Disable auto-start
sudo systemctl disable dashboard
```

## Key Bindings

| Key | Action |
|-----|--------|
| `Ctrl+C` | Gracefully exit (local mode) |
| `Ctrl+Alt+F1` | Switch to dashboard (tty1) |
| `Ctrl+Alt+F2` | Switch to login prompt (tty2) |

## Project Structure

```
kjt_python_ubuntu_dashboard/
├── main.py                 # Main entry point
├── config.py               # Configuration
├── system_stats.py          # CPU/RAM/Disk/Network/Process metrics
├── gpu_stats.py             # NVIDIA GPU via nvidia-smi
├── dashboard.py             # Rich layout builder
├── requirements.txt         # Python deps
├── README.md                # This file
├── systemd/
│   ├── dashboard.service    # Full replacement systemd unit
│   └── override.conf        # agetty autologin drop-in (alt)
└── scripts/
    ├── install_service.sh   # Deploy & enable
    └── uninstall_service.sh # Rollback
```

## Configuration

Edit `config.py` to customise:

- `REFRESH_INTERVAL` — update frequency (default: 1 second)
- `DISK_PATHS` — mount points to monitor (default: `["/"]`)
- `TOP_PROCESSES_COUNT` — number of processes per table (default: 5)
- `THRESHOLD_LOW` / `THRESHOLD_MED` — colour thresholds

## Troubleshooting

| Problem | Likely Fix |
|---------|------------|
| No GPU section | `nvidia-smi` not found or no NVIDIA GPU — hidden automatically |
| Dashboard doesn't appear on tty1 | Run `sudo systemctl status dashboard` to check for errors |
| `pip install` fails | Ensure `python3-pip` is installed: `sudo apt install python3-pip` |
| Service won't start | Check logs: `sudo journalctl -u dashboard -f` |
| Terminal artefacts after exit | Run `reset` in the terminal |

## Uninstall

```bash
sudo bash scripts/uninstall_service.sh
```

This restores getty@tty1 and optionally removes installed files and the
`dashboard` user.

## Architecture Decisions

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

## License

MIT
