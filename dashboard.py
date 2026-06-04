"""
Dashboard layout builder.

Constructs a ``rich.layout.Layout`` tree populated with styled panels,
bars, tables, and text based on the live system statistics dict.
"""

from typing import Dict, List

from rich.align import Align
from rich.columns import Columns
from rich.layout import Layout
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from config import (
    COLOR_CYAN,
    COLOR_DIM,
    COLOR_GREEN,
    COLOR_MAGENTA,
    COLOR_RED,
    COLOR_WHITE,
    COLOR_YELLOW,
    LAYOUT_CPU_RATIO,
    LAYOUT_DISK_RATIO,
    LAYOUT_DOCKER_ROW_RATIO,
    LAYOUT_FOOTER_RATIO,
    LAYOUT_GPU_RATIO,
    LAYOUT_HEADER_RATIO,
    LAYOUT_NET_RATIO,
    LAYOUT_ROW1_RATIO,
    LAYOUT_ROW2_RATIO,
    LAYOUT_ROW3_RATIO,
    THRESHOLD_LOW,
    THRESHOLD_MED,
)


# ── Colour Helpers ───────────────────────────────────────────────────────

def _bar_color(value: float) -> str:
    """Return a Rich colour name based on the percentage threshold."""
    if value <= THRESHOLD_LOW:
        return COLOR_GREEN
    if value <= THRESHOLD_MED:
        return COLOR_YELLOW
    return COLOR_RED


def _styled_bar(value: float, width: int = 20) -> Text:
    """Return a unicode progress bar string with colour."""
    filled = int(value / 100 * width)
    empty = width - filled
    color = _bar_color(value)
    bar = "█" * filled + "░" * empty
    return Text(bar, style=color)


def _pct_text(value: float) -> Text:
    """Return a coloured percentage text."""
    color = _bar_color(value)
    return Text(f"{value:.0f}%", style=color)


# ── Header ───────────────────────────────────────────────────────────────

def _build_header(stats: Dict) -> Panel:
    sysinfo = stats.get("system_info", {})
    hostname = sysinfo.get("hostname", "unknown")
    os_arch = sysinfo.get("os_arch", "unknown")
    uptime = stats.get("uptime", "N/A")
    load = stats.get("cpu", {}).get("load_avg", [])
    load_str = " ".join(str(x) for x in load)
    status = stats.get("status", "")

    text = Text.assemble(
        (" 🖥  SYSTEM MONITOR — ", COLOR_CYAN),
        (hostname, COLOR_WHITE, "bold"),
        ("\n", ""),
        (f" OS: {os_arch}", COLOR_DIM),
        ("   │   ", ""),
        (f"Uptime: {uptime}", COLOR_DIM),
        ("   │   ", ""),
        (f"Load: {load_str}", COLOR_DIM),
    )

    if status:
        if "\n" in status:
            lines = status.split("\n")
            status_text = Text(lines[0], style=COLOR_WHITE)
            for line in lines[1:]:
                status_text += Text("\n") + Text(line, style=COLOR_DIM)
            text += Text("\n") + status_text
        else:
            text += Text(f"\n{status}", style=COLOR_GREEN)

    return Panel(text, style=COLOR_DIM)


# ── CPU Panel ────────────────────────────────────────────────────────────

def _build_cpu_panel(stats: Dict) -> Panel:
    cpu = stats.get("cpu", {})
    overall = cpu.get("overall", 0)
    per_core = cpu.get("per_core", [])
    freq = cpu.get("frequency_mhz", 0)

    lines: List[Text] = []
    # Overall bar
    bar = _styled_bar(overall, width=30)
    pct = _pct_text(overall)
    lines.append(Text.assemble(
        ("CPU  ", COLOR_WHITE, "bold"),
        bar,
        (" ", ""),
        pct,
    ))

    # Per-core grid — 2 columns
    core_count = len(per_core)
    if core_count > 0:
        cols = max(2, core_count // 4 + 1)
        rows = (core_count + cols - 1) // cols
        grid_lines: List[str] = []
        for r in range(rows):
            row_parts = []
            for c in range(cols):
                idx = r + c * rows
                if idx < core_count:
                    val = per_core[idx]
                    core_bar = "█" * int(val / 100 * 8) + "░" * (8 - int(val / 100 * 8))
                    color = _bar_color(val)
                    row_parts.append(f"C{idx} [{color}]{core_bar}[/] {val:.0f}%")
            if row_parts:
                grid_lines.append("  ".join(row_parts))
        grid_text = "\n".join(grid_lines)
        lines.append(Text("\n") + Text.from_markup(grid_text))

    # Temperature
    cpu_temp = stats.get("cpu_temperature", {})
    if cpu_temp.get("available"):
        max_temp = cpu_temp["max"]
        temp_color = COLOR_GREEN if max_temp < 70 else (COLOR_YELLOW if max_temp < 85 else COLOR_RED)
        lines.append(Text(f"\nTemp: {max_temp:.0f}°C", style=temp_color))

    # Frequency
    lines.append(Text(f"\nFreq: {freq} MHz", style=COLOR_DIM))

    combined = lines[0]
    for l in lines[1:]:
        combined += Text("\n") + l

    return Panel(combined, title="[bold]CPU[/]", border_style=COLOR_CYAN)


# ── GPU Panel ────────────────────────────────────────────────────────────

def _build_gpu_panel(stats: Dict) -> Panel:
    gpus = stats.get("gpu", [])
    if not gpus:
        return Panel(
            Align.center(Text("No GPU detected", style=COLOR_DIM)),
            title="[bold]GPU[/]",
            border_style=COLOR_DIM,
        )

    gpu = gpus[0]
    name = gpu.get("name", "GPU")
    util = gpu.get("util_gpu", 0)
    mem_used = gpu.get("mem_used", 0)
    mem_total = gpu.get("mem_total", 0)
    mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0
    temp = gpu.get("temp", 0)
    power = gpu.get("power", 0)

    util_bar = _styled_bar(util, width=20)
    mem_bar = _styled_bar(mem_pct, width=20)

    text = Text.assemble(
        (f"{name}", COLOR_WHITE, "bold"),
        ("\nUtil: ", ""), util_bar, (" ", ""), _pct_text(util),
        ("\nMem:  ", ""), mem_bar, (" ", ""),
        (f"{mem_pct:.0f}%  ({mem_used:.0f}/{mem_total:.0f} MB)", ""),
        ("\nTemp: ", ""), (f"{temp:.0f}°C", COLOR_MAGENTA),
        ("   Power: ", ""), (f"{power:.0f}W", COLOR_YELLOW),
    )
    return Panel(text, title="[bold]GPU[/]", border_style=COLOR_MAGENTA)


# ── RAM Panel ────────────────────────────────────────────────────────────

def _build_ram_panel(stats: Dict) -> Panel:
    ram = stats.get("ram", {})
    percent = ram.get("percent", 0)
    used_gb = ram.get("used_gb", 0)
    total_gb = ram.get("total_gb", 0)

    bar = _styled_bar(percent, width=50)
    pct = _pct_text(percent)

    text = Text.assemble(
        ("RAM  ", COLOR_WHITE, "bold"),
        bar,
        (" ", ""),
        pct,
        ("   ", ""),
        (f"{used_gb} GB / {total_gb} GB", COLOR_DIM),
    )
    return Panel(text, title="[bold]Memory[/]", border_style=COLOR_GREEN)


# ── Disk Panel ───────────────────────────────────────────────────────────

def _build_disk_panel(stats: Dict) -> Panel:
    disks = stats.get("disk", [])
    if not disks:
        return Panel(Text("No disk data", style=COLOR_DIM), title="[bold]Disk[/]", border_style=COLOR_YELLOW)

    lines = []
    for disk in disks:
        mount = disk.get("mount", "/")
        pct = disk.get("percent", 0)
        used = disk.get("used_gb", 0)
        total = disk.get("total_gb", 0)
        bar = _styled_bar(pct, width=20)
        pct_t = _pct_text(pct)
        lines.append(
            Text.assemble(
                (f" {mount}: ", ""), bar, (" ", ""), pct_t,
                ("   ", ""), (f"{used}G / {total}G", COLOR_DIM),
            )
        )

    content = Text("\n").join(lines)
    return Panel(content, title="[bold]Disk[/]", border_style=COLOR_YELLOW)


# ── Network Panel ────────────────────────────────────────────────────────

def _build_network_panel(stats: Dict) -> Panel:
    net = stats.get("network", {})
    rx = net.get("rx_speed_kbs", 0)
    tx = net.get("tx_speed_kbs", 0)

    text = Text.assemble(
        (" NETWORK\n", COLOR_WHITE, "bold"),
        ("  ↓ RX: ", COLOR_GREEN), (f"{rx:.1f} KB/s", COLOR_WHITE),
        ("\n  ↑ TX: ", COLOR_CYAN), (f"{tx:.1f} KB/s", COLOR_WHITE),
    )
    return Panel(text, title="[bold]Network[/]", border_style=COLOR_CYAN)


# ── Top Processes Tables ─────────────────────────────────────────────────

_SORT_COLORS = {
    "pid": (COLOR_DIM, COLOR_YELLOW, "bold"),       # normal, active, highlight
    "name": (COLOR_WHITE, COLOR_YELLOW, "bold"),
    "cpu": (COLOR_CYAN, COLOR_YELLOW, "bold"),
    "mem": (COLOR_MAGENTA, COLOR_YELLOW, "bold"),
}


def _build_process_table(title: str, data_key: str, stats: Dict,
                         sort_col: str = "cpu") -> Table:
    """Build a process table with active sort column highlighted."""
    table = Table(
        title=title,
        title_style="bold",
        border_style=COLOR_DIM,
        header_style=COLOR_WHITE,
        show_lines=False,
        padding=(0, 1),
    )

    # Build column headers with active sort highlighted
    col_defs = [
        ("PID", "pid", "right", 6),
        ("NAME", "name", "left", 20),
        ("CPU%", "cpu", "right", 6),
        ("MEM%", "mem", "right", 6),
    ]
    for label, key, justify, width in col_defs:
        normal_color, active_color, active_style = _SORT_COLORS.get(
            key, (COLOR_DIM, COLOR_YELLOW, "bold")
        )
        is_active = (key == sort_col)
        col_style = f"{active_color} {active_style}" if is_active else normal_color
        suffix = " ▼" if is_active else ""
        table.add_column(
            f"{label}{suffix}",
            justify=justify,
            style=col_style,
            width=width,
        )

    processes = stats.get(data_key, [])
    for proc in processes:
        table.add_row(
            str(proc.get("pid", "")),
            proc.get("name", "")[:18],
            f"{proc.get('cpu_percent', 0):.1f}",
            f"{proc.get('mem_percent', 0):.1f}",
        )
    return table


# ── Docker Panel ─────────────────────────────────────────────────────────

def _build_docker_panel(stats: Dict) -> Panel:
    """Build a table panel showing running Docker containers."""
    containers = stats.get("docker", [])
    if not containers:
        return Panel(
            Align.center(Text("Docker not available or no containers running", style=COLOR_DIM)),
            title="[bold]Docker Containers[/]",
            border_style=COLOR_CYAN,
        )

    table = Table(
        title_style="bold",
        border_style=COLOR_DIM,
        header_style=COLOR_WHITE,
        show_lines=False,
        padding=(0, 1),
        box=None,
    )
    table.add_column("NAME", style=COLOR_CYAN, width=24)
    table.add_column("CPU%", justify="right", style=COLOR_WHITE, width=8)
    table.add_column("MEM%", justify="right", style=COLOR_MAGENTA, width=8)
    table.add_column("MEM USAGE", justify="right", style=COLOR_DIM, width=16)

    for c in containers:
        mem_str = f"{c.get('mem_used_mib', 0):.0f} / {c.get('mem_total_mib', 0):.0f} MiB"
        table.add_row(
            c.get("name", "")[:22],
            f"{c.get('cpu_percent', 0):.1f}%",
            f"{c.get('mem_percent', 0):.1f}%",
            mem_str,
        )

    return Panel(
        table,
        title=f"[bold]🐳 Docker Containers ({len(containers)})[/]",
        border_style=COLOR_CYAN,
    )


# ── Public API ───────────────────────────────────────────────────────────

def build_layout(stats: Dict) -> Layout:
    """Build the full ``rich.layout.Layout`` tree from a *stats* dict."""
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", ratio=LAYOUT_HEADER_RATIO),
        Layout(name="row1", ratio=LAYOUT_ROW1_RATIO),
        Layout(name="row2", ratio=LAYOUT_ROW2_RATIO),
        Layout(name="row3", ratio=LAYOUT_ROW3_RATIO),
        Layout(name="docker_row", ratio=LAYOUT_DOCKER_ROW_RATIO),
        Layout(name="footer", ratio=LAYOUT_FOOTER_RATIO),
    )

    # Header
    layout["header"].update(_build_header(stats))

    # Row 1: CPU | GPU
    layout["row1"].split_row(
        Layout(name="cpu_panel", ratio=LAYOUT_CPU_RATIO),
        Layout(name="gpu_panel", ratio=LAYOUT_GPU_RATIO),
    )
    layout["cpu_panel"].update(_build_cpu_panel(stats))
    layout["gpu_panel"].update(_build_gpu_panel(stats))

    # Row 2: RAM
    layout["row2"].update(_build_ram_panel(stats))

    # Row 3: Disk | Network
    layout["row3"].split_row(
        Layout(name="disk_panel", ratio=LAYOUT_DISK_RATIO),
        Layout(name="net_panel", ratio=LAYOUT_NET_RATIO),
    )
    layout["disk_panel"].update(_build_disk_panel(stats))
    layout["net_panel"].update(_build_network_panel(stats))

    # Docker containers row
    layout["docker_row"].update(_build_docker_panel(stats))

    # Footer: Top 5 CPU | Top 5 RAM
    layout["footer"].split_row(
        Layout(name="top_cpu"),
        Layout(name="top_mem"),
    )
    sort1 = stats.get("sort1", "cpu")
    sort2 = stats.get("sort2", "mem")
    layout["top_cpu"].update(
        _build_process_table("📊 TABLE 1", "top_cpu", stats, sort_col=sort1)
    )
    layout["top_mem"].update(
        _build_process_table("📊 TABLE 2", "top_mem", stats, sort_col=sort2)
    )

    return layout
