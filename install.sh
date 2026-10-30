#!/bin/sh
# Echo installer. Installs into this clone (.venv) and your home directory only.
# Usage: ./install.sh [--with-transcription[=cuda|cpu|rocm] | --without-transcription]
#                    [--with-studio | --without-studio]
#   --with-transcription alone picks the profile from the hardware: cuda for an NVIDIA GPU,
#   rocm for an AMD GPU, cpu otherwise. --with-studio adds Echo Studio (summaries and questions
#   from a language-model server you choose). Both choices are remembered for the next install.
set -eu

root=$(cd "$(dirname "$0")" && pwd)
profile_file="$root/.install-profile"
extensions_file="$root/.install-extensions"
bin_dir="$HOME/.local/bin"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
apps_dir="$data_home/applications"
icon_dir="$data_home/icons/hicolor/scalable/apps"

# The model needs about 5 GB of GPU memory (4.4 GB measured, plus the driver's share); a card
# with less transcribes on the processor anyway, so it gets the smaller processor build.
GPU_MIN_MIB=5800

nvidia_mib() {
    command -v nvidia-smi >/dev/null 2>&1 || return 1
    nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | sort -n | tail -1
}

detect_profile() {
    if command -v nvidia-smi >/dev/null 2>&1 || [ -e /proc/driver/nvidia ]; then
        mib=$(nvidia_mib || true)
        if [ -n "$mib" ] && [ "$mib" -lt "$GPU_MIN_MIB" ] 2>/dev/null; then echo cpu-small-gpu
        else echo cuda
        fi
    elif [ -e /dev/kfd ]; then echo rocm
    else echo cpu
    fi
}

profile=""
[ -f "$profile_file" ] && profile=$(cat "$profile_file")
[ "$profile" = full ] && profile=cuda  # installs from before the compute profiles
detected=no
studio=keep
for arg in "$@"; do
    case "$arg" in
        --with-transcription) profile=$(detect_profile); detected=yes
            [ "$profile" = cpu-small-gpu ] && { profile=cpu; small_gpu=yes; } ;;
        --with-transcription=cuda|--with-transcription=cpu|--with-transcription=rocm) profile=${arg#*=} ;;
        --without-transcription) profile=base ;;
        --with-studio) studio=yes ;;
        --without-studio) studio=no ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done
[ -n "$profile" ] || profile=base
case "$profile" in base|cuda|cpu|rocm) ;; *) echo "Unknown profile in $profile_file: $profile" >&2; exit 2 ;; esac

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

if [ "$detected" = yes ]; then
    case "$profile" in
        cuda) say "Found an NVIDIA GPU: installing transcription for CUDA." ;;
        rocm) say "Found an AMD GPU: installing transcription for ROCm." ;;
        cpu) if [ "${small_gpu:-}" = yes ]; then
                 say "The NVIDIA GPU has less than 6 GB of memory, too little for the model: transcription will run on the processor (slower)."
             else
                 say "No NVIDIA or AMD GPU found: transcription will run on the processor (slower)."
             fi ;;
    esac
    echo "To choose otherwise: ./install.sh --with-transcription=cuda|cpu|rocm"
fi
say "Installing Echo ($profile profile) into $root/.venv"
cd "$root"
# Explicitly, because distribution builds of uv (Fedora's) turn automatic Python downloads off.
uv python install --quiet "$(cat "$root/.python-version")"
if [ "$profile" = base ]; then
    uv sync --locked --no-dev
else
    uv sync --locked --no-dev --extra "$profile"
fi
echo "$profile" > "$profile_file"
if [ "$studio" = yes ]; then
    if [ -d "$root/src/echo_studio" ]; then
        echo "echo_studio" > "$extensions_file"
        say "Including Echo Studio"
    else
        echo "Echo Studio is not in this copy of Echo; installing without it." >&2
    fi
elif [ "$studio" = no ]; then
    rm -f "$extensions_file"
fi

say "Adding launcher and menu entry"
mkdir -p "$bin_dir" "$apps_dir" "$icon_dir"
ln -sf "$root/bin/echo-app" "$bin_dir/echo-app"
cp "$root/data/echo-app.svg" "$icon_dir/echo-app.svg"
sed "s|@LAUNCHER@|$root/bin/echo-app|" "$root/data/echo-app.desktop.in" > "$apps_dir/echo-app.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$apps_dir" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
# A running Plasma panel reads the icon folders once at login; without this it shows Echo with a
# blank icon until the next login. The signal is KDE's own "icons changed" broadcast.
command -v gdbus >/dev/null 2>&1 && gdbus emit --session --object-path /KIconLoader \
    --signal org.kde.KIconLoader.iconChanged 0 >/dev/null 2>&1 || true

echo
"$root/bin/echo-app" doctor --no-gpu || true
echo
case ":$PATH:" in
    *":$bin_dir:"*) say "Done. Open Echo from the application menu or run: echo-app" ;;
    *) say "Done. Open Echo from the application menu, or run: $bin_dir/echo-app"
       echo "($bin_dir is not on your PATH.)" ;;
esac
