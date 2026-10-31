#!/bin/sh
# Remove Echo's launcher, menu entry and environment. Recordings are kept.
# Usage: ./uninstall.sh [--purge]   (--purge also deletes recordings, settings and logs)
set -eu

root=$(cd "$(dirname "$0")" && pwd)
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
purge=no
[ "${1:-}" = "--purge" ] && purge=yes

rm -f "$HOME/.local/bin/echo-app" \
      "$data_home/applications/echo-app.desktop" \
      "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/echo-app.desktop" \
      "$data_home/icons/hicolor/scalable/apps/echo-app.svg"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$data_home/applications" 2>/dev/null || true
rm -rf "$root/.venv" "$root/.install-profile" "$root/.install-extensions"
echo "Removed the launcher, menu entry and $root/.venv"

data_dir="$data_home/echo"
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/echo/settings.toml" ]; then
    custom=$(sed -n 's/^data_dir = "\(.*\)"$/\1/p' "${XDG_CONFIG_HOME:-$HOME/.config}/echo/settings.toml")
    [ -n "$custom" ] && data_dir="$custom"
fi

if [ "$purge" = yes ]; then
    printf 'Delete ALL recordings and transcripts in %s? Type "delete" to confirm: ' "$data_dir"
    read -r answer
    if [ "$answer" = delete ]; then
        rm -rf "$data_dir" "${XDG_CONFIG_HOME:-$HOME/.config}/echo" "${XDG_STATE_HOME:-$HOME/.local/state}/echo"
        echo "Deleted recordings, settings and logs."
    else
        echo "Kept your recordings."
    fi
else
    echo "Your recordings are still in $data_dir"
fi
echo "Downloaded models (if any) stay in the Hugging Face cache: ~/.cache/huggingface/hub"
