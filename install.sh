#!/bin/sh
# Echo installer. Installs into this clone (.venv) and your home directory only.
# Usage: ./install.sh [--with-transcription | --without-transcription]
set -eu

root=$(cd "$(dirname "$0")" && pwd)
profile_file="$root/.install-profile"
bin_dir="$HOME/.local/bin"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
apps_dir="$data_home/applications"
icon_dir="$data_home/icons/hicolor/scalable/apps"

profile=""
[ -f "$profile_file" ] && profile=$(cat "$profile_file")
for arg in "$@"; do
    case "$arg" in
        --with-transcription) profile=full ;;
        --without-transcription) profile=base ;;
        -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done
[ -n "$profile" ] || profile=base

say() { if [ -t 1 ]; then printf '\033[1m%s\033[0m\n' "$*"; else printf '%s\n' "$*"; fi; }

# Package family from os-release (ID, then ID_LIKE), as `echo-app doctor` does.
family=other
if [ -r /etc/os-release ]; then
    ids=$(. /etc/os-release; echo "${ID:-} ${ID_LIKE:-}")
    for id in $ids; do
        case "$id" in
            fedora|rhel|centos) family=fedora; break ;;
            debian|ubuntu) family=debian; break ;;
            arch|archlinux) family=arch; break ;;
        esac
    done
fi
# pkg FEDORA_PKG DEBIAN_PKG ARCH_PKG: the install command for this distribution
pkg() {
    case "$family" in
        fedora) echo "sudo dnf install $1" ;;
        debian) echo "sudo apt install $2" ;;
        arch) echo "sudo pacman -S $3" ;;
        *) echo "install $2 with your package manager" ;;
    esac
}

if ! command -v uv >/dev/null 2>&1; then
    echo "Echo needs uv to install its own Python and dependencies." >&2
    case "$family" in
        fedora|arch) echo "Install it with:  $(pkg uv uv uv)" >&2 ;;
        *) echo "Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2 ;;
    esac
    exit 1
fi
command -v pw-record >/dev/null 2>&1 || echo "Warning: pw-record not found. Install it with: $(pkg pipewire-utils pipewire-bin pipewire)" >&2
command -v ffmpeg >/dev/null 2>&1 || echo "Warning: ffmpeg not found. Install it with: $(pkg ffmpeg-free ffmpeg ffmpeg)" >&2

say "Installing Echo ($profile profile) into $root/.venv"
cd "$root"
# Explicitly, because distribution builds of uv (Fedora's) turn automatic Python downloads off.
uv python install --quiet "$(cat "$root/.python-version")"
if [ "$profile" = full ]; then
    uv sync --locked --no-dev --extra worker
else
    uv sync --locked --no-dev
fi
echo "$profile" > "$profile_file"

say "Adding launcher and menu entry"
mkdir -p "$bin_dir" "$apps_dir" "$icon_dir"
ln -sf "$root/bin/echo-app" "$bin_dir/echo-app"
cp "$root/data/echo-app.svg" "$icon_dir/echo-app.svg"
sed "s|@LAUNCHER@|$root/bin/echo-app|" "$root/data/echo-app.desktop.in" > "$apps_dir/echo-app.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$apps_dir" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

echo
"$root/bin/echo-app" doctor --no-gpu || true
echo
case ":$PATH:" in
    *":$bin_dir:"*) say "Done. Open Echo from the application menu or run: echo-app" ;;
    *) say "Done. Open Echo from the application menu, or run: $bin_dir/echo-app"
       echo "($bin_dir is not on your PATH.)" ;;
esac
