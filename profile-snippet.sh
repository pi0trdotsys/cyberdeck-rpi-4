# Dopisz na końcu ~/.bash_profile (bash) albo ~/.zprofile (zsh)
# Uruchamia animację startową + tmux TYLKO gdy logujesz się na czystym tty1
# (nie odpali się np. w oknie terminala pod X, gdybyś kiedyś jednak włączył i3)

if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    if [ -z "$TMUX" ]; then
        bash ~/.config/tmux/boot.sh
        bash ~/.config/tmux/session.sh
    fi
fi
