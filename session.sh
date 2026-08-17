#!/usr/bin/env bash
# ~/.config/tmux/session.sh
# Uruchamia sesje tmux z dashboardem jako okno startowe.
# Ctrl-b c otwiera nowe okno do faktycznej pracy (nvim, ssh, itp),
# Ctrl-b n / Ctrl-b p przelacza miedzy oknami.

SESSION="main"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux attach -t "$SESSION"
    exit 0
fi

tmux new-session -d -s "$SESSION" -n dashboard
tmux send-keys -t "$SESSION:dashboard" 'python3 ~/.config/dashboard/dashboard.py' C-m

tmux attach -t "$SESSION"
