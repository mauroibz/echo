"""Self-check of prerequisites and install health. Used by `echo-app doctor` and Help > Doctor."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from . import features, models, paths, settings
from .fsutil import free_bytes

OK, WARN, FAIL = "ok", "warn", "fail"

# Decoders for the import formats we promise. AMR (old WhatsApp/Android voice notes) is a
# warning only: Fedora's ffmpeg-free lacks it; RPM Fusion's ffmpeg has it.
REQUIRED_DECODERS = {"opus": "Opus (WhatsApp voice notes)", "aac": "AAC (.m4a)",
                     "mp3": "MP3", "flac": "FLAC", "vorbis": "Ogg Vorbis",
                     "pcm_s16le": "WAV"}
OPTIONAL_DECODERS = {"amrnb": "AMR-NB (old voice notes)", "amrwb": "AMR-WB", "wmav2": "WMA"}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


# ---- distributions ----------------------------------------------------------------------------

FEDORA, DEBIAN, ARCH, OTHER, WINDOWS = "fedora", "debian", "arch", "other", "windows"
_FAMILIES = {"fedora": FEDORA, "rhel": FEDORA, "centos": FEDORA, "debian": DEBIAN, "ubuntu": DEBIAN,
             "arch": ARCH, "archlinux": ARCH}
_INSTALL = {FEDORA: "sudo dnf install", DEBIAN: "sudo apt install", ARCH: "sudo pacman -S", WINDOWS: "winget install"}


def parse_os_release(text: str) -> str:
    """The package family of an os-release file: ID first, then each ID_LIKE entry."""
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip('"').strip("'")
    for ident in [values.get("ID", "")] + values.get("ID_LIKE", "").split():
        if ident.lower() in _FAMILIES:
            return _FAMILIES[ident.lower()]
    return OTHER


@cache
def distro() -> str:
    if os.name == "nt":
        return WINDOWS
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            return parse_os_release(Path(path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return OTHER


def pkg_cmd(packages: dict[str, str], family: str | None = None) -> str:
    """The install command for this distribution, e.g. pkg_cmd({"fedora": "uv", "debian": ...})."""
    family = family or distro()
    if family in _INSTALL and packages.get(family):
        return f"{_INSTALL[family]} {packages[family]}"
    names = sorted({v for v in packages.values() if v})
    return f"Install {' or '.join(names)} with your package manager"


UV_HINT = {FEDORA: "sudo dnf install uv", ARCH: "sudo pacman -S uv", WINDOWS: "winget install astral-sh.uv",
           DEBIAN: "curl -LsSf https://astral.sh/uv/install.sh | sh",
           OTHER: "curl -LsSf https://astral.sh/uv/install.sh | sh"}
PIPEWIRE_TOOLS = {FEDORA: "pipewire-utils", DEBIAN: "pipewire-bin", ARCH: "pipewire"}
FFMPEG = {FEDORA: "ffmpeg-free", DEBIAN: "ffmpeg", ARCH: "ffmpeg", WINDOWS: "Gyan.FFmpeg"}
XCB_CURSOR = {FEDORA: "xcb-util-cursor", DEBIAN: "libxcb-cursor0", ARCH: "xcb-util-cursor"}
# Ubuntu 22.04 ships PipeWire but leaves audio with PulseAudio.
PULSE_TO_PIPEWIRE = {FEDORA: "pipewire-pulseaudio wireplumber", DEBIAN: "pipewire-audio-client-libraries wireplumber",
                     ARCH: "pipewire-pulse wireplumber"}


def _full_ffmpeg_hint(family: str) -> str:
    if family == FEDORA:
        return "Install the full ffmpeg from RPM Fusion: sudo dnf install ffmpeg --allowerasing"
    return "Install a full ffmpeg build: " + pkg_cmd(FFMPEG, family)


# ---- checks -----------------------------------------------------------------------------------

def check_pipewire() -> Check:
    missing = [c for c in ("pw-record", "pw-dump") if not _which(c)]
    if missing:
        return Check("PipeWire tools", FAIL, f"missing: {', '.join(missing)}", pkg_cmd(PIPEWIRE_TOOLS))
    return Check("PipeWire tools", OK, "pw-record and pw-dump found")


def _pw_dump() -> list[dict] | None:
    """pw-dump's objects, or None when it cannot run (no PipeWire daemon at all)."""
    import json

    try:
        r = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout or "[]")
    except ValueError:
        return None


def check_audio_nodes(dump: list[dict] | None = None, family: str | None = None) -> Check | None:
    """PipeWire running but owning no audio devices means PulseAudio still has them."""
    if dump is None:
        if not _which("pw-dump"):
            return None  # the tools check already failed
        dump = _pw_dump()
    family = family or distro()
    if dump is None:
        fix = "Start PipeWire: systemctl --user --now enable pipewire wireplumber"
        return Check("Audio devices", FAIL, "pw-dump could not reach PipeWire", fix)
    classes = {((o.get("info") or {}).get("props") or {}).get("media.class", "") for o in dump
               if o.get("type") == "PipeWire:Interface:Node"}
    if any(c.startswith(("Audio/Source", "Audio/Sink", "Audio/Duplex")) for c in classes):
        return Check("Audio devices", OK, "PipeWire manages the audio devices")
    fix = (f"{pkg_cmd(PULSE_TO_PIPEWIRE, family)} && systemctl --user --now enable wireplumber pipewire-pulse"
           "; then log out and back in.")
    if family == DEBIAN:
        fix += " Ubuntu 22.10 and newer use PipeWire for audio by default."
    return Check("Audio devices", FAIL,
                 "PipeWire is installed but not running the audio session (PulseAudio still owns audio)", fix)


def check_audio_backend() -> Check:
    """Which audio system Echo uses, and what that means for the user."""
    from .audio import backend

    try:
        which = backend.choose()
        b = backend.get()
        inputs = [s for s in b.list_sources() if s.kind == backend.INPUT]
    except Exception as e:  # noqa: BLE001 - any failure here is the finding
        return Check("Audio system", FAIL, f"no usable audio system: {e}", pkg_cmd(PIPEWIRE_TOOLS))
    if not inputs:
        return Check("Audio system", WARN, f"{which}: no inputs found", "Connect a microphone, then check again")
    if which == "pipewire":
        return Check("Audio system", OK, f"PipeWire, {len(inputs)} input{'s' if len(inputs) != 1 else ''}")
    note = "" if os.name == "nt" else " (PipeWire does not run the audio here: no computer audio or listening)"
    return Check("Audio system", WARN if note else OK,
                 f"PortAudio, {len(inputs)} input{'s' if len(inputs) != 1 else ''}{note}",
                 "" if not note else "Switching the session to PipeWire enables them; see the Audio devices line")


def _x11_session(env=None) -> bool:
    env = os.environ if env is None else env
    if env.get("XDG_SESSION_TYPE") == "x11":
        return True
    return bool(env.get("DISPLAY")) and not env.get("WAYLAND_DISPLAY")


def check_display(env=None, find_library=None) -> Check | None:
    """Qt's xcb platform plugin needs libxcb-cursor on X11 since Qt 6.5; Wayland does not."""
    if not _x11_session(env):
        return None
    if find_library is None:
        from ctypes.util import find_library
    if find_library("xcb-cursor") is None:
        return Check("Display libraries", FAIL, "X11 session without libxcb-cursor; the window cannot open",
                     pkg_cmd(XCB_CURSOR))
    return Check("Display libraries", OK, "X11 libraries found")


def ffmpeg_decoders() -> set[str]:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-decoders"], capture_output=True,
                         text=True, timeout=20).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "AVS":
            names.add(parts[1])
    return names


def check_ffmpeg() -> list[Check]:
    missing = [c for c in ("ffmpeg", "ffprobe") if not _which(c)]
    if missing:
        fix = pkg_cmd(FFMPEG) + ("  (or ffmpeg from RPM Fusion for AMR support)" if distro() == FEDORA else "")
        return [Check("ffmpeg", FAIL, f"missing: {', '.join(missing)}", fix)]
    try:
        dec = ffmpeg_decoders()
    except (OSError, subprocess.SubprocessError) as e:
        return [Check("ffmpeg", FAIL, f"could not run ffmpeg: {e}", "Reinstall ffmpeg")]
    checks = [Check("ffmpeg", OK, "ffmpeg and ffprobe found")]
    req_missing = [label for d, label in REQUIRED_DECODERS.items() if d not in dec]
    if req_missing:
        checks.append(Check("Audio decoders", FAIL, "missing: " + ", ".join(req_missing),
                            _full_ffmpeg_hint(distro())))
    else:
        checks.append(Check("Audio decoders", OK, "Opus, AAC, MP3, FLAC, Vorbis, WAV"))
    opt_missing = [label for d, label in OPTIONAL_DECODERS.items() if d not in dec]
    if opt_missing:
        checks.append(Check("Optional decoders", WARN, "missing: " + ", ".join(opt_missing),
                            "Only needed for those formats. " + (
                                "RPM Fusion's ffmpeg includes them." if distro() == FEDORA
                                else "A full ffmpeg build includes them.")))
    return checks


def check_python() -> Check:
    want = (paths.repo_root() / ".python-version")
    have = f"{sys.version_info.major}.{sys.version_info.minor}"
    pinned = want.read_text().strip() if want.exists() else have
    marker = f"{os.sep}uv{os.sep}python{os.sep}"
    managed = marker in sys.base_prefix or marker in os.path.realpath(sys.executable)
    if not have.startswith(pinned):
        return Check("Python", FAIL, f"running {have}, project pins {pinned}", "Run ./install.sh again")
    if not managed:
        return Check("Python", WARN, f"{have} at {sys.base_prefix} is not uv-managed",
                     "Run ./install.sh so uv provides its own interpreter")
    return Check("Python", OK, f"{sys.version.split()[0]} (uv-managed)")


def check_lock() -> Check:
    root = paths.repo_root()
    if not (root / "uv.lock").exists():
        return Check("Dependencies", WARN, "no uv.lock next to the source", "")
    uv = _which("uv")
    if not uv:
        return Check("Dependencies", WARN, "uv not found, cannot verify the lockfile", UV_HINT[distro()])
    r = subprocess.run([uv, "lock", "--check", "--offline"], cwd=root, capture_output=True,
                       text=True, timeout=60)
    if r.returncode != 0:
        return Check("Dependencies", FAIL, "uv.lock is out of date with pyproject.toml",
                     "Run: uv lock, review the diff, then ./install.sh")
    return Check("Dependencies", OK, "uv.lock in sync")


def check_data_dir(cfg: settings.Settings) -> list[Check]:
    d = cfg.data_path
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write-test"
        probe.write_bytes(b"x")
        probe.unlink()
    except OSError as e:
        return [Check("Data folder", FAIL, f"{d} is not writable: {e}", "Fix permissions or change data_dir in settings")]
    free = free_bytes(d)
    gb = free / 1e9
    hours = free / (cfg.sample_rate * 2 * cfg.channels) / 3600 / 0.55  # FLAC ~55% of PCM
    detail = f"{d}  ({gb:.1f} GB free, about {hours:,.0f} h of recording)"
    if gb < 1:
        st, fix = FAIL, "Free up disk space; recording refuses to start under 1 GB"
    elif gb < 5:
        st, fix = WARN, "Low disk space"
    else:
        st, fix = OK, ""
    return [Check("Data folder", st, detail, fix)]


def worker_installed() -> bool:
    return features.transcription_installed()


def check_profile(profile: str | None = None, hardware: str | None = None) -> Check:
    """The installed compute profile against the hardware install.sh would pick."""
    profile = profile or features.compute_profile()
    hardware = hardware or features.detected_hardware()
    from . import transcription

    detail = f"{profile}: runs on the {features.PROFILE_LABELS[profile]}"
    if profile == hardware:
        speed = transcription.speed_text()
        return Check("Compute profile", OK, detail + (f". {speed}" if speed else ""))
    if profile in (features.CUDA, features.ROCM) and hardware == features.CPU:
        gpu = "NVIDIA driver" if profile == features.CUDA else "AMD GPU (/dev/kfd)"
        return Check("Compute profile", WARN, f"{detail}, but no {gpu} was found",
                     "./install.sh --with-transcription=cpu  (a much smaller download that runs well on the processor)")
    return Check("Compute profile", WARN, f"{detail}, but this computer has an {features.PROFILE_LABELS[hardware]}",
                 f"./install.sh --with-transcription={hardware}")


def check_worker(gpu: bool = True) -> list[Check]:
    if not worker_installed():
        return [Check("Transcription", WARN, "transcription components not installed",
                      "./install.sh --with-transcription")]
    checks = [Check("Transcription", OK, "torch, transformers, peft, silero-vad installed"), check_profile()]
    if features.compute_profile() == features.CPU:
        cores = os.cpu_count() or 1
        checks.append(Check("Processor", OK if cores >= 4 else WARN, f"{cores} threads",
                            "" if cores >= 4 else "Transcription on fewer than 4 threads is slow"))
        gpu = False
    if gpu:
        code = ("import torch,json;ok=torch.cuda.is_available();"
                "print(json.dumps([ok, torch.cuda.get_device_name(0) if ok else '', "
                "torch.cuda.get_device_properties(0).total_memory if ok else 0, torch.__version__]))")
        try:
            r = subprocess.run([sys.executable, "-P", "-c", code], capture_output=True, text=True, timeout=120)
            import json
            ok, name, mem, ver = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as e:  # noqa: BLE001 - report anything as a failed check
            ok, name, mem, ver = False, "", 0, f"error: {e}"
        if ok and mem >= 7e9:
            checks.append(Check("GPU", OK, f"{name}, {mem / 2**30:.0f} GB (torch {ver})"))
        elif ok:
            checks.append(Check("GPU", WARN, f"{name} has {mem / 2**30:.0f} GB; 8 GB or more recommended",
                                "Transcription will use small batches"))
        elif features.compute_profile() == features.ROCM:
            checks.append(Check("GPU", WARN, "no AMD GPU visible to ROCm; transcription will run on CPU",
                                "Check that your user is in the render and video groups, then log in again"))
        else:
            driver = {FEDORA: "Install the NVIDIA driver (RPM Fusion akmod-nvidia)",
                      DEBIAN: "Install the NVIDIA driver: sudo ubuntu-drivers install",
                      ARCH: "Install the NVIDIA driver: sudo pacman -S nvidia",
                      WINDOWS: "Install the NVIDIA driver from nvidia.com"}.get(distro(), "Install the NVIDIA driver")
            checks.append(Check("GPU", WARN, "no CUDA GPU visible; transcription will run on CPU (slow)", driver))
    if not models.hf_token_present():
        checks.append(Check("Hugging Face login", FAIL if not models.all_cached() else OK,
                            "no token" if not models.all_cached() else "no token, but models are cached",
                            "Accept the model terms on huggingface.co, then: hf auth login"))
    else:
        checks.append(Check("Hugging Face login", OK, "token present"))
    if models.all_cached() and not models.speaker_cached():
        checks.append(Check("Speaker model", WARN, "not downloaded: recordings are not split by speaker",
                            "echo-app models download  (27 MB)"))
    missing = [r.repo for r in models.ALL if not models.is_cached(r)]
    if missing:
        checks.append(Check("Model files", WARN, "not downloaded yet: " + ", ".join(missing),
                            "echo-app models download  (about 4.3 GB)"))
    else:
        checks.append(Check("Model files", OK, "pinned revisions cached"))
    return checks


def run_all(gpu: bool = True) -> list[Check]:
    cfg, warning = settings.load()
    checks: list[Check] = []
    if warning:
        checks.append(Check("Settings", WARN, warning))
    if os.name != "nt":
        checks.append(check_pipewire())
        checks += [c for c in (check_audio_nodes(), check_display()) if c is not None]
    checks.append(check_audio_backend())
    checks += check_ffmpeg()
    checks.append(check_python())
    checks.append(check_lock())
    checks += check_data_dir(cfg)
    checks += check_worker(gpu=gpu)
    return checks


def render(checks: list[Check], color: bool = True) -> str:
    marks = {OK: ("✓", "32"), WARN: ("!", "33"), FAIL: ("✗", "31")}
    width = max(len(c.name) for c in checks)
    lines = []
    for c in checks:
        mark, code = marks[c.status]
        m = f"\033[{code}m{mark}\033[0m" if color else mark
        lines.append(f" {m} {c.name.ljust(width)}  {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"   {' ' * width}  → {c.fix}")
    return "\n".join(lines)


def main(args) -> int:
    checks = run_all(gpu=not args.no_gpu)
    print(render(checks, color=sys.stdout.isatty()))
    return 1 if any(c.status == FAIL for c in checks) else 0
