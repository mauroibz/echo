"""User settings: one flat TOML file with a default for every key."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import paths
from .fsutil import atomic_write_text

log = logging.getLogger(__name__)


@dataclass
class Settings:
    data_dir: str = ""  # empty means the XDG default
    source: str = ""  # PipeWire node name; empty means the system default source
    sample_rate: int = 48000
    channels: int = 1
    use_adapter: bool = True  # Spanish robustness LoRA on top of the base model
    auto_transcribe: bool = True  # queue transcription when a recording or import finishes
    worker_idle_minutes: int = 5
    theme: str = "light"  # light, dark or system
    show_timestamps: bool = False  # passage start times in the transcript margin
    language: str = "es"  # default transcription language
    edit_autopause: bool = True  # typing pauses a playing passage, which plays again a second later

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser() if self.data_dir else paths.default_data_dir()


_COMMENTS = {
    "data_dir": "Where recordings live. Empty = ~/.local/share/echo",
    "source": "PipeWire source node name. Empty = system default input",
    "sample_rate": "Recording sample rate in Hz",
    "channels": "1 = mono, 2 = stereo",
    "use_adapter": "Use the Spanish robustness adapter when transcribing",
    "auto_transcribe": "Transcribe new recordings and imports automatically",
    "worker_idle_minutes": "Minutes before the idle transcription worker exits and frees GPU memory",
    "theme": "Appearance: light, dark or system",
    "show_timestamps": "Show passage start times next to the transcript",
    "language": "Default transcription language (es, en, pt, fr, it, de, ...)",
    "edit_autopause": "While a passage plays for editing, typing pauses it and it plays again after",
}


def settings_path() -> Path:
    return paths.config_dir() / "settings.toml"


def load(path: Path | None = None) -> tuple[Settings, str | None]:
    """Return (settings, warning). A broken file is backed up and defaults are used."""
    path = path or settings_path()
    s = Settings()
    if not path.exists():
        return s, None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
        backup = path.with_suffix(".toml.bad")
        try:
            path.replace(backup)
        except OSError:
            pass
        msg = f"Settings file was unreadable ({e}); using defaults. Old file kept at {backup}"
        log.warning(msg)
        return s, msg
    for f in fields(Settings):
        if f.name in raw:
            value = raw[f.name]
            default = getattr(s, f.name)
            if type(value) is type(default):
                setattr(s, f.name, value)
            else:
                log.warning("Ignoring setting %s: expected %s", f.name, type(default).__name__)
    return s, None


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def save(s: Settings, path: Path | None = None) -> None:
    path = path or settings_path()
    lines = ["# Echo settings\n"]
    for k, v in asdict(s).items():
        lines.append(f"# {_COMMENTS.get(k, '')}\n{k} = {_toml_value(v)}\n")
    atomic_write_text(path, "\n".join(lines), mkdir=True)
