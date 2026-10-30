"""User settings: one flat TOML file with a default for every key."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import asdict, dataclass, field, fields
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
    your_name: str = ""  # who uses Echo: named in recordings by voice, and on the microphone side of calls
    computer_audio: bool = False  # also record what the default output plays, as a second track (calls)
    use_adapter: bool = True  # Spanish robustness LoRA on top of the base model
    auto_transcribe: bool = True  # queue transcription when a recording or import finishes
    worker_idle_minutes: int = 5
    theme: str = "light"  # light, dark or system
    show_timestamps: bool = False  # passage start times in the transcript margin
    language: str = "es"  # default transcription language
    edit_autopause: bool = True  # typing pauses a playing passage, which plays again a second later
    watch_dirs: list[str] = field(default_factory=list)  # folders whose new audio files are imported
    export_dir: str = ""  # Markdown folder (a vault) the library was last exported to
    export_sync: bool = False  # rewrite a recording's note there whenever it changes
    export_timestamps: bool = False  # paragraph times in exported notes
    export_audio: str = "link"  # link, copy or none
    global_shortcuts: bool = True  # Ctrl+Alt+R and Ctrl+Alt+N from any application (desktop portal)
    reduce_motion: bool = False  # no animations (also when the desktop has them off)

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser() if self.data_dir else paths.default_data_dir()


_COMMENTS = {
    "data_dir": "Where recordings live. Empty = ~/.local/share/echo",
    "source": "PipeWire source node name. Empty = system default input",
    "sample_rate": "Recording sample rate in Hz",
    "channels": "1 = mono, 2 = stereo",
    "your_name": "Your name: Echo names you in recordings by your voice, and on the microphone side of calls",
    "computer_audio": "Also record the computer audio (a call's other side) next to the microphone",
    "use_adapter": "Use the Spanish robustness adapter when transcribing",
    "auto_transcribe": "Transcribe new recordings and imports automatically",
    "worker_idle_minutes": "Minutes before the idle transcription worker exits and frees GPU memory",
    "theme": "Appearance: light, dark or system",
    "reduce_motion": "No animations in the window (Echo also follows the desktop's setting)",
    "show_timestamps": "Show passage start times next to the transcript",
    "language": "Default transcription language (es, en, pt, fr, it, de, ...)",
    "edit_autopause": "While a passage plays for editing, typing pauses it and it plays again after",
    "watch_dirs": "Folders whose new audio files are imported automatically (not their subfolders)",
    "export_dir": "Folder of Markdown notes the library is exported to",
    "export_sync": "Keep the exported notes up to date as recordings change (writes outside Echo's folder)",
    "export_timestamps": "Start exported paragraphs with their time",
    "export_audio": "Audio in exported notes: link (to Echo's file), copy, or none",
    "global_shortcuts": "Record and take quick notes with keys that work in any application",
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
            if type(value) is type(default) and (not isinstance(value, list) or all(isinstance(v, str) for v in value)):
                setattr(s, f.name, value)
            else:
                log.warning("Ignoring setting %s: expected %s", f.name, type(default).__name__)
    return s, None


def _toml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(str(x)) for x in v) + "]"
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
