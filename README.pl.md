<div align="center">

# cyberdeck-rpi-4

**Headless Raspberry Pi 4, okrojony do czystego terminalowego dashboardu.**

Bez X11. Bez Waylanda. Bez środowiska graficznego. Tylko `tty1`, `tmux` i Python.

[![Raspberry Pi OS](https://img.shields.io/badge/Raspberry_Pi_OS-Lite_64--bit-A22846?style=flat-square&logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/software/)
[![Python](https://img.shields.io/badge/Python-3-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![tmux](https://img.shields.io/badge/tmux-persistent_session-1BB91F?style=flat-square&logo=tmux&logoColor=white)](https://github.com/tmux/tmux)
[![Tailscale](https://img.shields.io/badge/Tailscale-mesh_networking-4B5BFF?style=flat-square&logo=tailscale&logoColor=white)](https://tailscale.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-000000?style=flat-square)](LICENSE)

[🇬🇧 English](README.md)&nbsp;&nbsp;|&nbsp;&nbsp;🇵🇱 Polski

</div>

---

## ⚠️ Status: praca w toku

To repo to fork-w-trakcie [`yoga11e-cyberdeck`](https://github.com/pi0trdotsys/cyberdeck),
adaptowany pod Raspberry Pi 4 z **ekranem dotykowym SPI 3.5" 480×320** zamiast panelu laptopa.

Co jest zrobione:
- Podstawowy system wgrany przez Raspberry Pi Imager (SSH + WiFi + hostname skonfigurowane)
- `dashboard.py` skopiowany, z poprawionymi ewidentnie błędnymi etykietami sprzętu (był
  zahardkodowany na Yogę 11e)

Co **nie** jest jeszcze zrobione:
- Sterownik/overlay ekranu dotykowego SPI nie jest skonfigurowany
- Layout dashboardu wciąż jest zaprojektowany pod pełny terminal (~130×37 znaków). **Nie** został
  przeprojektowany pod ~60×20 znaków, które faktycznie mieszczą się na panelu 480×320 — będzie
  wyglądał źle/ciasno na małym ekranie, dopóki to się nie zmieni
- Brak zrzutów ekranu — nic jeszcze nie działało na docelowym sprzęcie

Traktuj poniższą treść jako plan, nie gotową konfigurację, dopóki powyższe nie zostanie odhaczone.

## Czym to jest (stan docelowy)

`cyberdeck-rpi-4` zamienia Raspberry Pi 4 w dedykowaną, stale włączoną konsolę terminalową —
żywy dashboard systemowy, który bootuje prosto w pełnoekranowy `tty1` na małym ekranie SPI, bez
ekranu logowania, bez żadnej warstwy graficznej.

## Stos technologiczny

- **Raspberry Pi OS Lite (64-bit)** — czysta konsola, bez żadnego serwera graficznego
- **Python 3 + [`rich`](https://github.com/Textualize/rich)** — sam dashboard
- **tmux** — sesja przetrwa rozłączenie SSH
- **systemd** — autologin ograniczony wyłącznie do `tty1` (`tty2`–`tty6` zostają czystym loginem)
- **Tailscale** — dostęp do reszty floty urządzeń, status widoczny na żywo na dashboardzie

## Funkcje

- Panel informacji systemowych na żywo (OS, kernel, uptime, pakiety, CPU, pamięć, dysk)
- ASCII logo w stylu Debiana, kolorowane zgodnie ze stanem sprzętu/oprogramowania
- Obciążenie per-rdzeń CPU, paski pamięci/swapu/dysku — kolorowane progowo (zielony → żółty → czerwony)
- Przepustowość sieci (up/down)
- Sprawdzanie dostępności innych maszyn w sieci Tailscale na żywo
- Tabela najbardziej obciążających procesów
- Panele ze skrótami / szybkimi komendami / historią ostatnich komend
- Autologin ograniczony do `tty1` — pozostałe wirtualne terminale (`Alt`+`F2`..`F6`) zostają nietknięte do normalnej pracy

## Sprzęt (docelowy)

| | |
|---|---|
| Model | Raspberry Pi 4 Model B |
| Ekran | Dotykowy SPI 3.5" 480×320 |
| Dysk | microSD |
| Sieć | WiFi + sieć Tailscale |

> **Uwaga:** Pi nie ma baterii, więc panel/pole baterii z oryginalnego dashboardu Yogi jest tu
> martwym balastem — `psutil.sensors_battery()` po prostu zwraca `n/a`. Nie zostało jeszcze
> wycięte, skoro layout i tak czeka na przeprojektowanie.

## Instalacja

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
# najpierw popraw nazwę użytkownika wewnątrz getty-override.conf
sudo systemctl daemon-reload
sudo systemctl restart getty@tty1
```

Zmień w `dashboard.py` zmienne z nazwami hostów Tailscale na te, jakie pokazuje `tailscale status`
w Twojej własnej sieci.

Konfiguracja ekranu SPI i przeprojektowanie na kompaktowy layout są otwartymi zadaniami — nie są
jeszcze objęte powyższymi krokami instalacji.

## Architektura

```
    raspberrypi4 (tty1, ekran SPI)
             |
        sesja tmux
             |
        dashboard.py
             |
       sieć Tailscale
     /       |        \
 server   orangepipc2  yoga11e
(ThinkCentre)
```

## Licencja

MIT — zobacz [LICENSE](LICENSE).
