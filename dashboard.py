#!/usr/bin/env python3
"""
~/.config/dashboard/dashboard.py
QTechCore Cyberdeck (RPi4) - dashboard pod ekran SPI 3.5" (60x20, zielona faza fosforowa)

Trzy strony przelaczane automatycznie co PAGE_SECONDS: SYSTEM / DOCKER / NET.
Kluczowa metryka kazdej strony rysowana duzymi cyframi blokowymi (5 wierszy
wysokosci) - to daje "duze litery" bez zmiany fontu konsoli, ktora przy tym
ekranie kosztowalaby polowe dostepnych wierszy (patrz README).

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

PAGE_SECONDS = 6     # co ile sekund zmienia sie strona
TICK_SECONDS = 2     # co ile sekund odswiezaja sie dane

# Budzet ekranu 60x20: 2 wiersze na ramke + 1 header + 1 linia = 16 na tresc.
# Szerokosc: 60 - 2 (ramka) - 2 (padding) = 56.
# KAZDY element strony musi renderowac sie do DOKLADNIE jednego wiersza -
# zagniezdzona tabela/grid liczy sie jako 1 element, ale zajmuje N wierszy i
# rozwala budzet (tak sie wlasnie wysypala pierwsza wersja tej strony).
CONTENT_ROWS = 16
CONTENT_WIDTH = 56

# Paleta: monochromatyczna zielen (faza fosforowa CRT). Zolty/czerwony
# zarezerwowane pod ostrzezenia progowe i offline. Wyjatek: sama malinka jest
# czerwono-zielona, bo to ikona tozsamosciowa, nie metryka - w stalym rogu
# ekranu, wiec nie myli sie z alertem.
GREEN = "bold green"
DIM_GREEN = "green"
DIM = "dim green"

# Uwaga na znaki: fbcon renderuje klasyczny font VGA/codepage-437, nie pelny
# Unicode. Trzymamy sie wylacznie glifow z CP437: bloki " ░▒▓█", polbloki "▀▄",
# ramki "─│┌┐└┘═║╔╗╚╝", punktor "•". Nie-CP437 znaki (np. ▁▂▃▄▅▆▇ sparkline'ow
# albo cwiartki ▖▗▘▝) wyjda jako puste pola.
# Bez spacji na poziomie zerowym - inaczej przy braku ruchu sieciowego caly
# wykres znika i wyglada jak zepsuty zamiast jak plaska linia bazowa.
HIST_CHARS = "░▒▓█"

# Malinka 13x10. Poprzednia wersja (gladka kula + szypulka) czytala sie jako
# WISNIA - malina to owoc zbiorowy, wiec o rozpoznawalnosci decyduja widoczne
# pestkowce i ksztalt naparstkowy (szeroka gora, zwezajacy sie dol), a nie sama
# czerwien. Stad wzor dwutonowy: '#' to jasny pestkowiec, '.' to ciemniejszy
# szew miedzy nimi, a kolejne rzedy sa przesuniete wzgledem siebie.
RASPBERRY_PATTERN = [
    ("  \u2584\u2588\u2584   \u2584\u2588\u2584  ", True),
    ("  \u2580\u2588\u2588\u2584 \u2584\u2588\u2588\u2580  ", True),
    ("     \u2580\u2588\u2580     ", True),
    (" ##.##.##.## ", False),
    ("##.##.##.##.#", False),
    ("  ##.##.##.##", False),
    (" ##.##.##.## ", False),
    ("  #.##.##.#  ", False),
    ("   ##.##.##  ", False),
    ("    \u2580###\u2580    ", False),
]


def raspberry_row(idx):
    """Buduje jeden wiersz malinki jako Text z kolorowaniem per-znak."""
    pattern, leaf = RASPBERRY_PATTERN[idx]
    bright = "bold green" if leaf else "bold red"
    row = Text()
    for ch in pattern:
        if ch == " ":
            row.append(" ")
        elif ch == "#":
            row.append("\u2588", style=bright)
        elif ch == ".":
            row.append("\u2591", style="red")  # szew miedzy pestkowcami
        else:
            row.append(ch, style=bright)
    return row


# Cyfry blokowe 3x5 - naglowkowa metryka kazdej strony.
BIG_GLYPHS = {
    "0": ["███", "█ █", "█ █", "█ █", "███"],
    "1": ["  █", "  █", "  █", "  █", "  █"],
    "2": ["███", "  █", "███", "█  ", "███"],
    "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"],
    "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"],
    "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"],
    "9": ["███", "█ █", "███", "  █", "███"],
    "%": ["█ █", "  █", " █ ", "█  ", "█ █"],
    "K": ["█ █", "█ █", "██ ", "█ █", "█ █"],
    "-": ["   ", "   ", "███", "   ", "   "],
    " ": ["   ", "   ", "   ", "   ", "   "],
}

_host_check_cache = {}


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                        stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


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


def big_lines(s, style, indent=" "):
    """Zamienia napis na 5 wierszy Text z duzych cyfr blokowych."""
    rows = [indent] * 5
    for ch in s:
        glyph = BIG_GLYPHS.get(ch.upper(), BIG_GLYPHS[" "])
        for i in range(5):
            rows[i] += glyph[i] + " "
    return [Text(r, style=style) for r in rows]


def compose(left, art, left_width=43):
    """Skleja wiersz tresci z kolumna art-u po prawej - jeden Text, jeden wiersz.
    Dzieki temu budzet wierszy da sie liczyc wprost (patrz CONTENT_ROWS)."""
    row = left.copy()
    row.truncate(left_width, pad=True)
    row.append_text(art)
    return row


def hist_bar(values):
    vmax = max(values) or 1
    idx_max = len(HIST_CHARS) - 1
    return "".join(HIST_CHARS[min(int((v / vmax) * idx_max), idx_max)] for v in values)


def threshold_color(pct, low=40, high=75):
    """Zielony ponizej low, zolty do high, czerwony powyzej."""
    if pct < low:
        return "green"
    if pct < high:
        return "yellow"
    return "bold red"


def bar(pct, width=10, filled_char="█", empty_char="░"):
    filled = int((pct / 100) * width)
    return filled_char * filled + empty_char * (width - filled)


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
    return info.get("PRETTY_NAME", "Unknown").replace("GNU/Linux ", "")


def get_cpu_temp():
    """Temperatura SoC w stopniach C. /sys zamiast vcgencmd - dziala bez
    dodatkowych uprawnien i bez pakietu raspi-utils."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def get_local_ip():
    out = run("hostname -I")
    return out.split()[0] if out else "?"


def get_tailscale_ip():
    out = run("tailscale ip -4 2>/dev/null")
    return out.splitlines()[0] if out else "-"


def get_docker_containers():
    """Lista (nazwa, status). Pusta jesli docker niedostepny bez sudo."""
    out = run("docker ps -a --format '{{.Names}}\t{{.Status}}' 2>/dev/null")
    if not out:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            rows.append((parts[0], parts[1]))
    return rows


_last_net = psutil.net_io_counters()
_net_hist = deque([0] * 24, maxlen=24)
_net_rates = {"down": 0.0, "up": 0.0}


def sample_net():
    global _last_net
    net_now = psutil.net_io_counters()
    down = max(net_now.bytes_recv - _last_net.bytes_recv, 0) / TICK_SECONDS
    up = max(net_now.bytes_sent - _last_net.bytes_sent, 0) / TICK_SECONDS
    _last_net = net_now
    _net_hist.append(down + up)
    _net_rates["down"], _net_rates["up"] = down, up


def pad_rows(rows, target=CONTENT_ROWS):
    """Kazda strona ma ta sama wysokosc - inaczej ramka 'skacze' przy zmianie.
    Przycina tez kazdy Text do CONTENT_WIDTH, zeby zaden wiersz nie zawinal sie
    na nastepny i nie zjadl budzetu (Rule zostawiamy - sam sie dopasowuje)."""
    out = []
    for row in rows[:target]:
        if isinstance(row, Text):
            row = row.copy()
            row.truncate(CONTENT_WIDTH)
        out.append(row)
    return out + [Text("")] * (target - len(out))


def page_system():
    per_cpu = psutil.cpu_percent(percpu=True)
    cpu_avg = sum(per_cpu) / len(per_cpu) if per_cpu else 0
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load1, _, _ = psutil.getloadavg()
    temp = get_cpu_temp()

    uptime_s = time.time() - psutil.boot_time()
    h, m = int(uptime_s // 3600), int((uptime_s % 3600) // 60)

    temp_str = f"{temp:.0f}C" if temp is not None else "n/a"

    # Lewa kolumna: 8 wierszy zestawionych 1:1 z 8 wierszami malinki.
    left = [
        Text(""),
        Text("  CPU LOAD", style=DIM_GREEN),
        *big_lines(f"{cpu_avg:.0f}%", threshold_color(cpu_avg), indent="  "),
        Text(""),
        Text.assemble(("  Ld ", DIM_GREEN), (f"{load1:.2f}", GREEN),
                      ("   Temp ", DIM_GREEN),
                      (temp_str, threshold_color(temp or 0, 60, 75))),
        Text(""),
    ]

    rows = []
    for i in range(len(RASPBERRY_PATTERN)):
        cell = left[i] if i < len(left) else Text("")
        rows.append(compose(cell, raspberry_row(i)))

    # Rdzenie: tylko 4 na Pi 4, ale ograniczamy jawnie - na maszynie z 8+
    # rdzeniami linia inaczej zawijala sie na nastepny wiersz.
    core_str = " ".join(f"{p:>3.0f}" for p in per_cpu[:4])

    rows += [
        Rule(style=DIM),
        Text.assemble((" Cores ", DIM_GREEN), (core_str, DIM_GREEN),
                      ("   Up ", DIM_GREEN), (f"{h}h{m:02d}m", GREEN)),
        Text.assemble((" Mem  ", DIM_GREEN), (bar(mem.percent, 20), threshold_color(mem.percent)),
                      (f" {mem.percent:>3.0f}%", threshold_color(mem.percent)),
                      (f" {mem.used/1e9:.1f}G", DIM_GREEN)),
        Text.assemble((" Swap ", DIM_GREEN), (bar(swap.percent, 20), threshold_color(swap.percent, 20, 60)),
                      (f" {swap.percent:>3.0f}%", threshold_color(swap.percent, 20, 60))),
        Text.assemble((" Disk ", DIM_GREEN), (bar(disk.percent, 20), threshold_color(disk.percent)),
                      (f" {disk.percent:>3.0f}%", threshold_color(disk.percent)),
                      (f" {disk.used/1e9:.0f}/{disk.total/1e9:.0f}G", DIM_GREEN)),
        Text.assemble((" ", DIM), (get_os_release(), DIM_GREEN)),
    ]
    return pad_rows(rows)


def page_docker():
    containers = get_docker_containers()
    running = [c for c in containers if c[1].lower().startswith("up")]

    rows = [
        Text(" CONTAINERS RUNNING", style=DIM_GREEN),
        *big_lines(f"{len(running)}", GREEN if running else DIM),
        Text.assemble(("  ", DIM), (f"{len(running)}", GREEN), (" up / ", DIM_GREEN),
                      (f"{len(containers) - len(running)}", DIM_GREEN), (" stopped", DIM_GREEN)),
        Rule(style=DIM),
    ]

    if not containers:
        rows.append(Text(" (brak kontenerow - docker ps -a)", style=DIM))
    else:
        # 9 wierszy na liste; jesli kontenerow wiecej, ostatni wiersz mowi ile
        # zostalo ukrytych - obciecie ma byc widoczne, nie ciche.
        limit = 8 if len(containers) <= 8 else 7
        for name, status in containers[:limit]:
            up = status.lower().startswith("up")
            style = "green" if up else "bold red"
            row = Text(" ", style=style)
            row.append("█ " if up else "░ ", style=style)
            row.append(f"{name[:20]:<20} ", style=DIM_GREEN)
            row.append(status[:24], style=style)
            rows.append(row)
        hidden = len(containers) - limit
        if hidden > 0:
            rows.append(Text(f"   +{hidden} wiecej", style=DIM))

    return pad_rows(rows)


def page_net():
    down_k = _net_rates["down"] / 1024
    up_k = _net_rates["up"] / 1024

    rows = [
        Text(" DOWNLINK  KB/S", style=DIM_GREEN),
        *big_lines(f"{down_k:.0f}K", GREEN),
        Text(""),
        Text.assemble(("  up ", DIM_GREEN), (f"{up_k:>7.1f} KB/s", GREEN)),
        Text.assemble(("  ", DIM), (hist_bar(_net_hist), GREEN),
                      ("  ", DIM), (f"peak {max(_net_hist)/1024:.0f}K", DIM_GREEN)),
        Rule(style=DIM),
        Text(" » MESH", style=GREEN),
    ]

    for host in (THINKCENTRE_HOST, ORANGEPI_HOST, YOGA_HOST):
        text, style = check_host(host)
        row = Text(" ", style=style)
        row.append("█ " if "online" in text else "░ ", style=style)
        row.append(f"{host:<16}", style=DIM_GREEN)
        row.append(text, style=style)
        rows.append(row)

    rows += [
        Rule(style=DIM),
        Text.assemble((" lan ", DIM_GREEN), (get_local_ip(), GREEN),
                      ("   ts ", DIM_GREEN), (get_tailscale_ip(), GREEN)),
    ]

    return pad_rows(rows)


PAGES = [("SYSTEM", page_system), ("DOCKER", page_docker), ("NET", page_net)]


def build_frame(page_idx):
    name, builder = PAGES[page_idx]
    hostname = os.uname().nodename
    now = datetime.now().strftime("%d.%m %H:%M")

    header = Table.grid(expand=True)
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        Text.assemble((f" {hostname}", GREEN), ("  » ", DIM), (name, GREEN)),
        Text(f"{now} ", style=DIM_GREEN),
    )

    # Wskaznik strony blokami - CP437-safe, czytelny nawet przy 8x16.
    dots = Text()
    for i in range(len(PAGES)):
        dots.append("███" if i == page_idx else "░░░", style=GREEN if i == page_idx else DIM)
        dots.append(" ", style=DIM)

    body = [header, Rule(style=DIM_GREEN)] + builder()

    return Panel(
        Group(*body),
        box=box.DOUBLE,
        border_style=GREEN,
        title="QTECHCORE // RPI4",
        title_align="center",
        subtitle=dots,
        subtitle_align="center",
        padding=(0, 1),
    )


def main():
    # color_system="standard" - konsola fbcon renderuje na realnym Linux VT,
    # ktory ma tylko 16 kolorow ANSI, nie 256/truecolor jak terminal pod SSH.
    console = Console(color_system="standard")
    started = time.time()
    with Live(build_frame(0), console=console, refresh_per_second=1, screen=True) as live:
        while True:
            time.sleep(TICK_SECONDS)
            sample_net()
            page_idx = int((time.time() - started) / PAGE_SECONDS) % len(PAGES)
            live.update(build_frame(page_idx))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h", end="", flush=True)  # zawsze przywroc kursor
