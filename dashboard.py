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
from datetime import datetime

from rich.console import Console, Group
from rich.text import Text
from rich.rule import Rule
from rich.live import Live

import psutil

THINKCENTRE_HOST = "server"      # ThinkCentre M715q, nazwa z `tailscale status`
ORANGEPI_HOST = "orangepipc2"    # Orange Pi PC2, nazwa z `tailscale status`
YOGA_HOST = "yoga11e"            # Lenovo Yoga 11e, nazwa z `tailscale status`

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


_last_net = psutil.net_io_counters()


def build_frame():
    """Caly ekran to jeden gesty widok - 60x20 nie ma miejsca na wiele paneli."""
    global _last_net

    hostname = os.uname().nodename
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    per_cpu = psutil.cpu_percent(percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load1, load5, load15 = psutil.getloadavg()

    uptime_s = time.time() - psutil.boot_time()
    h, m = int(uptime_s // 3600), int((uptime_s % 3600) // 60)

    net_now = psutil.net_io_counters()
    down_delta = max(net_now.bytes_recv - _last_net.bytes_recv, 0)
    up_delta = max(net_now.bytes_sent - _last_net.bytes_sent, 0)
    _last_net = net_now

    lines = []

    header = Text(f" {hostname:<10}", style=CYAN)
    header.append(f"{now}", style=BODY)
    lines.append(header)
    lines.append(Rule(style=DIM_GREEN))

    lines.append(Text(f"{get_os_release()}", style=DEBIAN_RED))
    lines.append(Text(f"{os.uname().release}", style=CYAN))
    lines.append(Text.assemble(
        ("Up ", CYAN), (f"{h}h{m:02d}m", BODY),
        ("   Pkgs ", CYAN), (f"{get_pkg_count()}", BODY),
    ))

    core_str = " ".join(f"{i+1}:{pct:>3.0f}%" for i, pct in enumerate(per_cpu))
    lines.append(Text(f"CPU {core_str}", style=threshold_color(max(per_cpu, default=0))))
    lines.append(Text(
        f"Load {load1:.2f} {load5:.2f} {load15:.2f}", style=CYAN,
    ))

    lines.append(Text.assemble(
        ("Mem  ", BODY), (bar(mem.percent, 10), threshold_color(mem.percent)),
        (f" {mem.percent:>3.0f}%", threshold_color(mem.percent)),
        ("  Swap ", BODY), (bar(swap.percent, 6), threshold_color(swap.percent, 20, 60)),
        (f" {swap.percent:>3.0f}%", threshold_color(swap.percent, 20, 60)),
    ))
    lines.append(Text.assemble(
        ("Disk ", BODY), (bar(disk.percent, 10), threshold_color(disk.percent)),
        (f" {disk.percent:>3.0f}%", threshold_color(disk.percent)),
        (f"  {disk.used/1e9:.1f}/{disk.total/1e9:.0f}G", BODY),
    ))
    lines.append(Text(
        f"Net  down {down_delta/1024:>5.1f}K/s  up {up_delta/1024:>5.1f}K/s",
        style=BLUE,
    ))

    lines.append(Rule(style=DIM_GREEN))
    lines.append(Text(" MESH", style=MAGENTA))
    for host in (THINKCENTRE_HOST, ORANGEPI_HOST, YOGA_HOST):
        text, style = check_host(host)
        row = Text(f" {host:<13}", style=BLUE)
        row.append(text, style=style)
        lines.append(row)

    return Group(*lines)


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
