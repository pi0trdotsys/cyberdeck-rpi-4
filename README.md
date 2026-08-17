<div align="center">

# cyberdeck-rpi-4

**A headless Raspberry Pi 4, stripped down to a pure-terminal dashboard.**

No X11. No Wayland. No desktop environment. Just `tty1`, `tmux`, and Python.

[![Raspberry Pi OS](https://img.shields.io/badge/Raspberry_Pi_OS-Lite_64--bit-A22846?style=flat-square&logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/software/)
[![Python](https://img.shields.io/badge/Python-3-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![tmux](https://img.shields.io/badge/tmux-persistent_session-1BB91F?style=flat-square&logo=tmux&logoColor=white)](https://github.com/tmux/tmux)
[![Tailscale](https://img.shields.io/badge/Tailscale-mesh_networking-4B5BFF?style=flat-square&logo=tailscale&logoColor=white)](https://tailscale.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-000000?style=flat-square)](LICENSE)

🇬🇧 English&nbsp;&nbsp;|&nbsp;&nbsp;[🇵🇱 Polski](README.pl.md)

</div>

---

## ⚠️ Status: work in progress

This repo is a fork-in-progress of [`yoga11e-cyberdeck`](https://github.com/pi0trdotsys/cyberdeck),
adapted for a Raspberry Pi 4 driving a **3.5" 480×320 SPI touchscreen** instead of a laptop panel.

What's done:
- Base OS flashed via Raspberry Pi Imager (SSH + WiFi + hostname preconfigured)
- `dashboard.py` copied over with the obviously-wrong hardware labels fixed (was hardcoded to
  the Yoga 11e)

What's **not** done yet:
- The SPI touchscreen driver/overlay is not configured
- The dashboard layout is still sized for a full terminal (~130×37 chars). It has **not** been
  redesigned for the ~60×20 chars a 480×320 panel actually fits — it will look wrong/cramped on
  the small screen until that pass happens
- No screenshots yet — nothing has run on the actual target hardware

Track progress before relying on anything below as a finished setup.

## What this is (target state)

`cyberdeck-rpi-4` turns a Raspberry Pi 4 into a dedicated, always-on terminal console — a live
system dashboard that boots directly into a full-screen `tty1` on a small SPI display, no login
prompt, no graphical stack.

## Stack

- **Raspberry Pi OS Lite (64-bit)** — pure console, no display server at all
- **Python 3 + [`rich`](https://github.com/Textualize/rich)** — the dashboard itself
- **tmux** — persistent session, survives SSH disconnects
- **systemd** — autologin scoped to `tty1` only (`tty2`–`tty6` stay clean logins)
- **Tailscale** — mesh access to the rest of the fleet, status shown live on the dashboard

## Features

- Live system info panel (OS, kernel, uptime, packages, CPU, memory, disk)
- Debian-style ASCII logo, colored to match hardware/software state
- Per-core CPU load, memory/swap/disk bars — all threshold-colored (green → yellow → red)
- Network throughput (up/down)
- Live reachability check for other machines on the Tailscale mesh
- Top processes table
- Shortcuts / quick-commands / recent-commands reference panels
- Autologin scoped to `tty1` — other virtual terminals (`Alt`+`F2`..`F6`) stay untouched for normal work

## Hardware (target)

| | |
|---|---|
| Model | Raspberry Pi 4 Model B |
| Display | 3.5" 480×320 SPI touchscreen |
| Storage | microSD |
| Network | WiFi + Tailscale mesh |

> **Note:** a Pi has no battery, so the battery panel/field from the original Yoga dashboard is
> effectively dead weight here — `psutil.sensors_battery()` just returns `n/a`. It hasn't been
> ripped out yet since the layout is getting redesigned anyway.

## Install

```bash
sudo apt install -y python3-rich python3-psutil tmux figlet cmatrix curl

mkdir -p ~/.config/dashboard ~/.config/tmux
cp dashboard.py       ~/.config/dashboard/dashboard.py
cp tmux.conf          ~/.config/tmux/tmux.conf
cp boot.sh            ~/.config/tmux/boot.sh
cp session.sh         ~/.config/tmux/session.sh
chmod +x ~/.config/dashboard/dashboard.py ~/.config/tmux/*.sh
echo "source-file ~/.config/tmux/tmux.conf" >> ~/.tmux.conf

cat profile-snippet.sh >> ~/.bash_profile

sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo cp getty-override.conf /etc/systemd/system/getty@tty1.service.d/override.conf
# edit the username inside getty-override.conf first
sudo systemctl daemon-reload
sudo systemctl restart getty@tty1
```

Edit `dashboard.py` to point the Tailscale host variables at whatever hostnames show up in
`tailscale status` for your own mesh.

SPI screen setup and the compact-layout redesign are tracked as open work — not covered by the
install steps above yet.

## Architecture

```
      raspberrypi4 (tty1, SPI screen)
             |
        tmux session
             |
        dashboard.py
             |
      Tailscale mesh
     /       |        \
 server   orangepipc2  yoga11e
(ThinkCentre)
```

## License

MIT — see [LICENSE](LICENSE).
