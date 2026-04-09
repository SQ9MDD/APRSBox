#!/bin/sh
set -eu

if command -v systemctl >/dev/null 2>&1; then
    exec systemctl reboot
fi

if command -v reboot >/dev/null 2>&1; then
    exec reboot
fi

printf '%s\n' "No reboot command found."
exit 1
