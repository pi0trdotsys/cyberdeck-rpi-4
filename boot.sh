#!/usr/bin/env bash
# ~/.config/tmux/boot.sh
# QTechCore Cyberdeck (RPi4) - animacja startowa przy logowaniu na tty1

GREEN='\033[38;2;51;255;51m'
DIMGREEN='\033[38;2;20;140;20m'
RESET='\033[0m'

clear

# 2 sekundy "matrix rain" w klasycznej zieleni fosforowej
if command -v cmatrix >/dev/null 2>&1; then
    timeout 2 cmatrix -C green -b
fi

clear

# Krótki "glitch" tekst powitalny
GREETING="QTECHCORE // RPI4 CYBERDECK"
for i in 1 2 3; do
    clear
    echo -e "${DIMGREEN}$(echo "$GREETING" | sed 's/./&\ /g' | fold -w1 | shuf | tr -d '\n')${RESET}"
    sleep 0.08
done
clear
echo -e "${GREEN}${GREETING}${RESET}"
sleep 0.4
clear
