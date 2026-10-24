"""Self-check of prerequisites and install health. Used by `echo-app doctor` and Help > Doctor."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
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


def check_pipewire() -> Check:
    missing = [c for c in ("pw-record", "pw-dump") if not _which(c)]
    if missing:
        return Check("PipeWire tools", FAIL, f"missing: {', '.join(missing)}",
                     "sudo dnf install pipewire-utils")
    return Check("PipeWire tools", OK, "pw-record and pw-dump found")


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
        return [Check("ffmpeg", FAIL, f"missing: {', '.join(missing)}",
                      "sudo dnf install ffmpeg-free  (or ffmpeg from RPM Fusion for AMR support)")]
    try:
        dec = ffmpeg_decoders()
    except (OSError, subprocess.SubprocessError) as e:
        return [Check("ffmpeg", FAIL, f"could not run ffmpeg: {e}", "Reinstall ffmpeg")]
    checks = [Check("ffmpeg", OK, "ffmpeg and ffprobe found")]
    req_missing = [label for d, label in REQUIRED_DECODERS.items() if d not in dec]
    if req_missing:
        checks.append(Check("Audio decoders", FAIL, "missing: " + ", ".join(req_missing),
                            "Install a full ffmpeg build (RPM Fusion: sudo dnf install ffmpeg --allowerasing)"))
    else:
        checks.append(Check("Audio decoders", OK, "Opus, AAC, MP3, FLAC, Vorbis, WAV"))
    opt_missing = [label for d, label in OPTIONAL_DECODERS.items() if d not in dec]
    if opt_missing:
        checks.append(Check("Optional decoders", WARN, "missing: " + ", ".join(opt_missing),
                            "Only needed for those formats. RPM Fusion's ffmpeg includes them."))
    return checks


def check_python() -> Check:
    want = (paths.repo_root() / ".python-version")
    have = f"{sys.version_info.major}.{sys.version_info.minor}"
    pinned = want.read_text().strip() if want.exists() else have
    managed = "/uv/python/" in sys.base_prefix or "/uv/python/" in os.path.realpath(sys.executable)
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
        return Check("Dependencies", WARN, "uv not found, cannot verify the lockfile",
                     "sudo dnf install uv")
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


def check_worker(gpu: bool = True) -> list[Check]:
    if not worker_installed():
        return [Check("Transcription", WARN, "transcription components not installed",
                      "./install.sh --with-transcription")]
    checks = [Check("Transcription", OK, "torch, transformers, peft, silero-vad installed")]
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
        else:
            checks.append(Check("GPU", WARN, "no CUDA GPU visible; transcription will run on CPU (slow)",
                                "Install the NVIDIA driver (RPM Fusion akmod-nvidia)"))
    if not models.hf_token_present():
        checks.append(Check("Hugging Face login", FAIL if not models.all_cached() else OK,
                            "no token" if not models.all_cached() else "no token, but models are cached",
                            "Accept the model terms on huggingface.co, then: hf auth login"))
    else:
        checks.append(Check("Hugging Face login", OK, "token present"))
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
    checks.append(check_pipewire())
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
