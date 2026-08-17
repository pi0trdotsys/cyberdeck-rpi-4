#!/usr/bin/env python3
"""
~/.config/dashboard/dashboard.py
QTechCore Cyberdeck (RPi4) - dashboard kompaktowy pod ekran SPI 3.5" (60x20, zielona faza fosforowa)
Wymaga: python3-rich, python3-psutil
"""

import os
import re
import subprocess
import time
from collections import deque
from datetime import datetime

from rich.console import Console, Group
from rich.text import Text
from rich.rule import Rule
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich import box

import psutil

THINKCENTRE_HOST = "server"      # ThinkCentre M715q, nazwa z `tailscale status`
ORANGEPI_HOST = "orangepipc2"    # Orange Pi PC2, nazwa z `tailscale status`
YOGA_HOST = "yoga11e"            # Lenovo Yoga 11e, nazwa z `tailscale status`

DOCKER_ROWS = 3  # ile wierszy stale zarezerwowanych na status kontenerow

_host_check_cache = {}


def check_host(host, cache_seconds=8):
    """Ping do dowolnego hosta Tailscale, wynik cache'owany per-host (domyslnie 8s)."""
    now = time.time()
    cached = _host_check_cache.get(host)
    if cached and now - cached["last"] < cache_seconds:
        return cached["text"], cached["style"]

    result = run(f"ping -c 1 -W 1 {host} 2>/dev/null")
    match = re.search(r"time=([\d.]+)", result) if result else None
    if match:
        entry = {"text": f"online {float(match.group(1)):.0f}ms", "style": "green", "last": now}
    else:
        entry = {"text": "offline", "style": "bold red", "last": now}

    _host_check_cache[host] = entry
    return entry["text"], entry["style"]


GREEN = "bold green"
DIM_GREEN = "green"
BODY = "white"
DEBIAN_RED = "bold red"
CYAN = "bold cyan"
YELLOW = "bold yellow"
MAGENTA = "bold magenta"
BLUE = "bold blue"
DIM = "dim white"

# Uwaga na znaki: fbcon na tym ekranie renderuje klasyczny font VGA/codepage-437,
# nie pelny Unicode jak terminal pod SSH. Trzymamy sie wylacznie glifow z CP437
# (blok pelny/cien: " ░▒▓█", pojedyncza ramka "─│┌┐└┘", punktor "•") - inaczej
# nie-CP437 znaki (np. osemkowe bloki sparkline'ow ▁▂▃▄▅▆▇) wyjda jako puste pola.
HIST_CHARS = " ░▒▓█"


def hist_bar(values):
    vmax = max(values) or 1
    idx_max = len(HIST_CHARS) - 1
    return "".join(HIST_CHARS[min(int((v / vmax) * idx_max), idx_max)] for v in values)


# Mala pixel-artowa malina (oryginalna, uproszczona grafika blokowa - nie kopia
# logo Raspberry Pi) - listek + jagoda, wylacznie znak "█" z CP437, kolorowany.
# 6 wierszy, zeby zestawic 1:1 z 6 liniami statystyk obok (bez kosztu wierszy).
RASPBERRY_ART = [
    (" ▓▓  ▓▓ ", "green"),
    (" ██████ ", "green"),
    ("██  ██  ", "bold red"),
    ("████████", "red"),
    (" ██  ██ ", "bold red"),
    ("████████", "red"),
]


def threshold_color(pct, low=40, high=75):
    """Zielony ponizej low, zolty do high, czerwony powyzej."""
    if pct < low:
        return "green"
    if pct < high:
        return "yellow"
    return "bold red"


def bar(pct, width=10, filled_char="|", empty_char="-"):
    filled = int((pct / 100) * width)
    return "[" + filled_char * filled + empty_char * (width - filled) + "]"


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                        stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def get_os_release():
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v.strip('"')
    except FileNotFoundError:
        pass
    return info.get("PRETTY_NAME", "Unknown")


def get_pkg_count():
    out = run("dpkg -l | grep -c '^ii'")
    return out or "?"


def get_docker_containers():
    """Lista (nazwa, status) ze wszystkich kontenerow (dzialajace i zatrzymane).
    Pusta lista jesli docker nie jest zainstalowany / dostepny bez sudo."""
    out = run("docker ps -a --format '{{.Names}}\t{{.Status}}' 2>/dev/null")
    if not out:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            rows.append((parts[0], parts[1]))
    return rows


def build_docker_lines():
    """Zawsze zwraca dokladnie DOCKER_ROWS wierszy - stale miejsce w layoucie.
    Jesli kontenerow jest wiecej niz sie miesci, ostatni wiersz to '+N more',
    zeby obciecie bylo widoczne, a nie ciche."""
    containers = get_docker_containers()
    if not containers:
        rows = [Text(" (brak kontenerow)", style=DIM)]
        rows += [Text("")] * (DOCKER_ROWS - len(rows))
        return rows

    show_n = DOCKER_ROWS if len(containers) <= DOCKER_ROWS else DOCKER_ROWS - 1
    rows = []
    for name, status in containers[:show_n]:
        running = status.lower().startswith("up")
        style = "green" if running else "bold red"
        row = Text(" • ", style=style)
        row.append(f"{name[:13]:<13} ", style=BLUE)
        row.append(status[:18], style=style)
        rows.append(row)

    remaining = len(containers) - show_n
    if remaining > 0:
        rows.append(Text(f" +{remaining} more (docker ps -a)", style=DIM))
    while len(rows) < DOCKER_ROWS:
        rows.append(Text(""))
    return rows


_last_net = psutil.net_io_counters()
_net_hist = deque([0] * 10, maxlen=10)  # skrocone z 20 - zwolnione miejsce zajela ikona malinki obok


def build_frame():
    """Caly ekran to jeden gesty widok w ramce - 60x20 nie ma miejsca na wiele paneli."""
    global _last_net

    hostname = os.uname().nodename
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    per_cpu = psutil.cpu_percent(percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load1, _, _ = psutil.getloadavg()

    uptime_s = time.time() - psutil.boot_time()
    h, m = int(uptime_s // 3600), int((uptime_s % 3600) // 60)

    net_now = psutil.net_io_counters()
    down_delta = max(net_now.bytes_recv - _last_net.bytes_recv, 0)
    up_delta = max(net_now.bytes_sent - _last_net.bytes_sent, 0)
    _last_net = net_now
    _net_hist.append(down_delta + up_delta)

    lines = []

    header = Text(f" {hostname:<10}", style=CYAN)
    header.append(f"{now}", style=BODY)
    lines.append(header)
    lines.append(Rule(style=DIM_GREEN))

    core_str = " ".join(f"{i+1}:{pct:>3.0f}%" for i, pct in enumerate(per_cpu))

    stat_lines = [
        Text(f"{get_os_release()}", style=DEBIAN_RED),
        Text.assemble(
            ("Up ", CYAN), (f"{h}h{m:02d}m", BODY),
            ("   Pkgs ", CYAN), (f"{get_pkg_count()}", BODY),
        ),
        Text.assemble(
            (f"CPU {core_str}  ", threshold_color(max(per_cpu, default=0))),
            (f"Ld {load1:.2f}", CYAN),
        ),
        Text.assemble(
            ("Mem ", BODY), (bar(mem.percent, 14), threshold_color(mem.percent)),
            (f" {mem.percent:>3.0f}%", threshold_color(mem.percent)),
            ("  Swap ", BODY), (bar(swap.percent, 8), threshold_color(swap.percent, 20, 60)),
            (f" {swap.percent:>3.0f}%", threshold_color(swap.percent, 20, 60)),
        ),
        Text.assemble(
            ("Disk ", BODY), (bar(disk.percent, 24), threshold_color(disk.percent)),
            (f" {disk.percent:>3.0f}%", threshold_color(disk.percent)),
            (f"  {disk.used/1e9:.1f}/{disk.total/1e9:.0f}G", BODY),
        ),
        Text.assemble(
            ("Net  ", BLUE), (hist_bar(_net_hist), CYAN),
            (f"  down {down_delta/1024:>5.1f}K  up {up_delta/1024:>5.1f}K", BLUE),
        ),
    ]

    # Statystyki + mala malina obok, w tym samym zestawie wierszy (bez kosztu
    # dodatkowych wierszy - wykorzystuje tylko wolne miejsce w poziomie).
    stats_grid = Table.grid(expand=True, padding=(0, 1))
    stats_grid.add_column(ratio=1)
    stats_grid.add_column(width=8)
    for i, stat_line in enumerate(stat_lines):
        icon_text, icon_style = RASPBERRY_ART[i] if i < len(RASPBERRY_ART) else ("", "")
        stats_grid.add_row(stat_line, Text(icon_text, style=icon_style))
    lines.append(stats_grid)

    lines.append(Rule(style=DIM_GREEN))
    lines.append(Text(" DOCKER", style=MAGENTA))
    lines.extend(build_docker_lines())

    lines.append(Text(" MESH", style=MAGENTA))
    for host in (THINKCENTRE_HOST, ORANGEPI_HOST, YOGA_HOST):
        text, style = check_host(host)
        row = Text(" • ", style=style)
        row.append(f"{host:<13}", style=BLUE)
        row.append(text, style=style)
        lines.append(row)

    return Panel(
        Group(*lines),
        box=box.SQUARE,
        border_style=DIM_GREEN,
        title="QTECHCORE // RPI4",
        title_align="center",
        padding=(0, 1),
    )


def main():
    # color_system="standard" - konsola fbcon renderuje na realnym Linux VT,
    # ktory ma tylko 16 kolorow ANSI, nie 256/truecolor jak terminal pod SSH.
    console = Console(color_system="standard")
    with Live(build_frame(), console=console, refresh_per_second=1, screen=True) as live:
        while True:
            time.sleep(2)
            live.update(build_frame())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h", end="", flush=True)  # zawsze przywroc kursor
