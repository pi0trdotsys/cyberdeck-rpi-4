#!/usr/bin/env python3
"""
~/.config/dashboard/dashboard.py
QTechCore Cyberdeck - pelny dashboard (zielona faza fosforowa)
Wymaga: python3-rich, python3-psutil
"""

import os
import re
import subprocess
import time
from datetime import datetime
from collections import deque

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich import box

import psutil

THINKCENTRE_HOST = "server"      # ThinkCentre M715q, nazwa z `tailscale status`
ORANGEPI_HOST = "orangepipc2"    # Orange Pi PC2, nazwa z `tailscale status`

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
FAINT = "dim green"
BODY = "white"

# Paleta rozszerzona - dla urozmaicenia (zamiast czystego monochromu)
DEBIAN_RED = "bold red"
CYAN = "bold cyan"
YELLOW = "bold yellow"
MAGENTA = "bold magenta"
BLUE = "bold blue"
WHITE = "bold white"

DEBIAN_LOGO = r'''   _,met$$$$$gg.
,g$$$$$$$$$$$$$$$P.
$$$P"     """Y$$.".
$$$'              `$$$.
$$$        ,ggs.    `$$b:
$$$'     ,$P"'  .    $$$
$$:      $$.    -   ,d$$'
$$;      Y$b._  _,d$P'
Y$$.    `.`"Y$$$$P"'
'''


def threshold_color(pct, low=40, high=75):
    """Zielony ponizej low, zolty do high, czerwony powyzej."""
    if pct < low:
        return "green"
    if pct < high:
        return "yellow"
    return "bold red"


def color_swatch_row():
    blocks = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    t = Text()
    for c in blocks:
        t.append("██", style=c)
    return t

# --- Historia dla sparkline sieci ---
net_hist_down = deque([0] * 30, maxlen=30)
net_hist_up = deque([0] * 30, maxlen=30)
_last_net = psutil.net_io_counters()

SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def sparkline(values):
    vmax = max(values) or 1
    out = ""
    for v in values:
        idx = int((v / vmax) * (len(SPARK_CHARS) - 1))
        out += SPARK_CHARS[idx]
    return out


def bar(pct, width=14, filled_char="|", empty_char="-"):
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


def get_cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    return line.split(":")[1].strip()
    except FileNotFoundError:
        pass
    return "Unknown CPU"


def get_pkg_count():
    out = run("dpkg -l | grep -c '^ii'")
    return out or "?"


def get_wifi_signal():
    out = run("/usr/sbin/iw dev wlp1s0 link 2>/dev/null | grep -i signal")
    if "signal" in out:
        try:
            dbm = int(out.split(":")[1].strip().split()[0])
            # bardzo zgrubne mapowanie dBm -> %
            pct = max(0, min(100, 2 * (dbm + 100)))
            return f"{pct}%"
        except Exception:
            return "?"
    return "down"


def build_header():
    hostname = os.uname().nodename
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cpu_pct = psutil.cpu_percent()
    ram_pct = psutil.virtual_memory().percent
    batt = psutil.sensors_battery()
    bat_pct = f"{int(batt.percent)}%" if batt else "n/a"
    wifi = get_wifi_signal()

    left = Text(f" {hostname}  ", style=CYAN)
    left.append("debian-13  ", style=DEBIAN_RED)
    left.append("[~]", style=BODY)

    center = Text(f"[----- {now} -----]", style=BODY)

    right = Text(" cpu ", style=BODY)
    right.append(f"{cpu_pct:>3.0f}% ", style=threshold_color(cpu_pct))
    right.append(" ram ", style=BODY)
    right.append(f"{ram_pct:>3.0f}% ", style=threshold_color(ram_pct))
    right.append(" bat ", style=BODY)
    right.append(f"{bat_pct:>4} ", style=MAGENTA)
    right.append(" wifi ", style=BODY)
    right.append(f"{wifi} ", style=BLUE)

    table = Table.grid(expand=True)
    table.add_column(justify="left")
    table.add_column(justify="center")
    table.add_column(justify="right")
    table.add_row(left, center, right)
    return Panel(table, box=box.SQUARE, style=GREEN, border_style=DIM_GREEN)


def build_info_panel():
    glyph = Text(DEBIAN_LOGO.rstrip("\n"), style=DEBIAN_RED)

    uptime_s = time.time() - psutil.boot_time()
    h = int(uptime_s // 3600)
    m = int((uptime_s % 3600) // 60)

    disk = psutil.disk_usage("/")
    mem = psutil.virtual_memory()
    batt = psutil.sensors_battery()

    # (etykieta, wartosc, styl_etykiety)
    rows = [
        ("OS", get_os_release(), DEBIAN_RED),
        ("Host", "Raspberry Pi 4 Model B", WHITE),
        ("Kernel", os.uname().release, CYAN),
        ("Uptime", f"{h}h {m}m", CYAN),
        ("Packages", f"{get_pkg_count()} (dpkg)", CYAN),
        ("Shell", os.environ.get("SHELL", "?").split("/")[-1], YELLOW),
        ("WM", "none (tty)", YELLOW),
        ("Terminal", os.environ.get("TERM", "?"), YELLOW),
        ("CPU", get_cpu_model(), MAGENTA),
        ("Memory",
         f"{mem.used / 1e9:.2f} GiB / {mem.total / 1e9:.2f} GiB ({mem.percent:.0f}%)",
         threshold_color(mem.percent)),
        ("Disk",
         f"{disk.used / 1e9:.1f} / {disk.total / 1e9:.1f} GiB ({disk.percent:.0f}%)",
         threshold_color(disk.percent)),
        ("Battery",
         f"{int(batt.percent)}% [{'Charging' if batt.power_plugged else 'Discharging'}]" if batt else "n/a",
         "green" if (batt and batt.power_plugged) else threshold_color(100 - (batt.percent if batt else 100), 40, 75)),
    ]

    info_table = Table.grid(padding=(0, 2))
    info_table.add_column(no_wrap=True)
    info_table.add_column()
    for label, val, style in rows:
        info_table.add_row(Text(label, style=style), Text(val, style=BODY))

    swatch = color_swatch_row()

    motto = Text("Tools don't make the hacker. Curiosity does. - Null Byte", style=BODY)

    content = Group(glyph, info_table, motto)
    return Panel(content, title="piotr@raspberrypi4", box=box.SQUARE,
                 border_style=DIM_GREEN, title_align="left")


def build_system_monitor():
    global _last_net
    per_cpu = psutil.cpu_percent(percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    batt = psutil.sensors_battery()

    net_now = psutil.net_io_counters()
    down_delta = net_now.bytes_recv - _last_net.bytes_recv
    up_delta = net_now.bytes_sent - _last_net.bytes_sent
    _last_net = net_now
    net_hist_down.append(max(down_delta, 0))
    net_hist_up.append(max(up_delta, 0))

    lines = []
    core_str = "  ".join(f"{i+1}:{pct:>3.0f}%" for i, pct in enumerate(per_cpu))
    lines.append(Text(f"CPU   {core_str}", style=threshold_color(max(per_cpu))))
    lines.append(Text(
        f"Load  {psutil.getloadavg()[0]:.2f} {psutil.getloadavg()[1]:.2f} {psutil.getloadavg()[2]:.2f}",
        style=CYAN,
    ))
    lines.append(Text(
        f"Mem   {bar(mem.percent, 10)} {mem.percent:>3.0f}%   Swap {bar(swap.percent, 6)} {swap.percent:>3.0f}%",
        style=threshold_color(mem.percent),
    ))

    if batt:
        bstyle = "green" if batt.power_plugged else threshold_color(100 - batt.percent, 40, 75)
        batt_str = f"{batt.percent:>3.0f}% {'Chg' if batt.power_plugged else 'Dis'}"
    else:
        bstyle = "white"
        batt_str = "n/a"
    lines.append(Text(
        f"Bat   {batt_str}    Disk {bar(disk.percent, 6)} {disk.percent:>3.0f}%",
        style=bstyle,
    ))

    lines.append(Text(
        f"Net   down {down_delta/1024:>6.1f}K/s  up {up_delta/1024:>6.1f}K/s",
        style=BLUE,
    ))

    tc_text, tc_style = check_host(THINKCENTRE_HOST)
    op_text, op_style = check_host(ORANGEPI_HOST)
    ts_line = Text("TS    TC: ", style=BLUE)
    ts_line.append(tc_text, style=tc_style)
    ts_line.append("   OPi: ", style=BLUE)
    ts_line.append(op_text, style=op_style)
    lines.append(ts_line)

    return Panel(Group(*lines), title="SYSTEM MONITOR", box=box.SQUARE,
                 border_style=DIM_GREEN, title_align="left")


def build_top_processes():
    procs = []
    for p in psutil.process_iter(["pid", "username", "cpu_percent", "memory_percent", "name"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)

    table = Table(box=box.SIMPLE, expand=True, border_style=FAINT)
    table.add_column("PID", style=CYAN, justify="right")
    table.add_column("USER", style=MAGENTA)
    table.add_column("CPU%", justify="right")
    table.add_column("MEM%", style=BLUE, justify="right")
    table.add_column("COMMAND", style=WHITE)

    for p in procs[:8]:
        cpu_val = p.get("cpu_percent") or 0
        table.add_row(
            str(p.get("pid")),
            (p.get("username") or "?")[:8],
            Text(f"{cpu_val:.1f}", style=threshold_color(cpu_val, 15, 40)),
            f"{p.get('memory_percent') or 0:.1f}",
            p.get("name") or "?",
        )

    return Panel(table, title="TOP PROCESSES", box=box.SQUARE,
                 border_style=DIM_GREEN, title_align="left")


def build_shortcuts():
    # To sa proponowane skroty - dzialaja jesli skonfigurujesz triggerhappy
    # (patrz README), same z siebie nie sa jeszcze podpiete pod klawisze.
    items = [
        ("Super+Enter", "Terminal (nowe okno tmux)"),
        ("Super+d", "Menu (fzf-based launcher)"),
        ("Super+n", "Notatki (nvim ~/notes.md)"),
        ("Super+1-5", "Przelacz TTY"),
        ("Super+Shift+r", "Przeladuj config"),
    ]
    table = Table.grid(padding=(0, 2))
    table.add_column(style=YELLOW)
    table.add_column(style=BODY)
    for k, v in items:
        table.add_row(k, v)
    return Panel(table, title="SHORTCUTS (planowane)", box=box.SQUARE,
                 border_style=DIM_GREEN, title_align="left")


def build_quick_commands():
    items = [
        ("update", "sudo apt update && sudo apt upgrade"),
        ("weather", "curl wttr.in"),
        ("ports", "ss -tulnp"),
        ("disk", "df -h"),
        ("temp", "sensors"),
    ]
    table = Table.grid(padding=(0, 2))
    table.add_column(style=CYAN)
    table.add_column(style=BODY)
    for k, v in items:
        table.add_row(k, v)
    return Panel(table, title="QUICK COMMANDS", box=box.SQUARE,
                 border_style=DIM_GREEN, title_align="left")


def build_recent_commands():
    histfile = os.path.expanduser("~/.bash_history")
    lines = []
    try:
        with open(histfile) as f:
            lines = f.readlines()[-6:]
    except FileNotFoundError:
        lines = []

    table = Table.grid(padding=(0, 1))
    table.add_column(style=BODY)
    if not lines:
        table.add_row(Text("(brak - uruchom 'history -a' albo poczekaj na nowe komendy)", style=BODY))
    for line in lines:
        table.add_row(Text(line.strip(), style=BODY))

    return Panel(table, title="RECENT COMMANDS", box=box.SQUARE,
                 border_style=DIM_GREEN, title_align="left")


def build_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="bottom", size=10),
    )
    layout["main"].split_row(
        Layout(name="info"),
        Layout(name="right"),
    )
    layout["right"].split_column(
        Layout(name="monitor"),
        Layout(name="procs"),
    )
    layout["bottom"].split_row(
        Layout(name="shortcuts"),
        Layout(name="quick"),
        Layout(name="recent"),
    )
    return layout


def render(layout):
    layout["header"].update(build_header())
    layout["info"].update(build_info_panel())
    layout["monitor"].update(build_system_monitor())
    layout["procs"].update(build_top_processes())
    layout["shortcuts"].update(build_shortcuts())
    layout["quick"].update(build_quick_commands())
    layout["recent"].update(build_recent_commands())


def main():
    console = Console()
    layout = build_layout()
    with Live(layout, console=console, refresh_per_second=1, screen=True):
        while True:
            render(layout)
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h", end="", flush=True)  # zawsze przywroc kursor
