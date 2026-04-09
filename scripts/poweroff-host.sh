#!/bin/sh
set -eu

if command -v systemctl >/dev/null 2>&1; then
    exec systemctl poweroff
fi

if command -v poweroff >/dev/null 2>&1; then
    exec poweroff
fi

printf '%s\n' "No poweroff command found."
exit 1
