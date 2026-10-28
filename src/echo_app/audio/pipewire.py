"""PipeWire integration through its command-line tools (stdlib only)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

INPUT = "input"
MONITOR = "monitor"


@dataclass(frozen=True)
class Source:
    name: str  # PipeWire node.name, used as the capture target
    description: str
    kind: str  # INPUT or MONITOR
    channels: int | None = None
    is_default: bool = False

    @property
    def label(self) -> str:
        if self.kind == MONITOR:
            return f"Computer audio: {self.description}"
        return self.description

    @property
    def short_label(self) -> str:
        """The label without the channel-layout suffix PipeWire adds ("Analog Stereo" and the like)."""
        d = re.sub(r"\s+(Analog|Digital|Pro)?\s*(Stereo|Mono|Surround[\s\d.]*)(\s*\(.*?\))?(?=$|\s*\[)", "",
                   self.description).strip() or self.description
        return f"Computer audio: {d}" if self.kind == MONITOR else d


# The second track of a call recording: whatever the default output plays. No target, so WirePlumber
# links the capture to the current default output's monitor and moves it when the default changes.
DEFAULT_OUTPUT = Source("", "Default output", MONITOR, None, True)


def _pw_dump() -> list[dict]:
    out = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=10, check=True).stdout
    return json.loads(out)


def parse_sources(dump: list[dict]) -> list[Source]:
    default_source = default_sink = None
    for o in dump:
        if o.get("type") == "PipeWire:Interface:Metadata" and o.get("props", {}).get("metadata.name") == "default":
            for m in o.get("metadata") or []:
                value = m.get("value")
                name = value.get("name") if isinstance(value, dict) else None
                if m.get("key") == "default.audio.source":
                    default_source = name
                elif m.get("key") == "default.audio.sink":
                    default_sink = name
    inputs, monitors = [], []
    for o in dump:
        if o.get("type") != "PipeWire:Interface:Node":
            continue
        p = (o.get("info") or {}).get("props") or {}
        cls = p.get("media.class", "")
        name = p.get("node.name")
        if not name:
            continue
        desc = p.get("node.description") or p.get("node.nick") or name
        ch = p.get("audio.channels")
        if cls in ("Audio/Source", "Audio/Source/Virtual", "Audio/Duplex"):
            inputs.append(Source(name, desc, INPUT, ch, name == default_source))
        elif cls == "Audio/Sink":
            monitors.append(Source(name, desc, MONITOR, ch, name == default_sink))
    inputs.sort(key=lambda s: (not s.is_default, s.description.lower()))
    monitors.sort(key=lambda s: (not s.is_default, s.description.lower()))
    return inputs + monitors


def list_sources() -> list[Source]:
    try:
        return parse_sources(_pw_dump())
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def default_source(sources: list[Source] | None = None) -> Source | None:
    sources = list_sources() if sources is None else sources
    for s in sources:
        if s.kind == INPUT and s.is_default:
            return s
    return next((s for s in sources if s.kind == INPUT), None)


def find(name: str, sources: list[Source] | None = None) -> Source | None:
    sources = list_sources() if sources is None else sources
    return next((s for s in sources if s.name == name), None)


def resolve(preferred: str, sources: list[Source] | None = None) -> tuple[Source | None, str | None]:
    """Pick the preferred source, or the default with a note if it is missing."""
    sources = list_sources() if sources is None else sources
    if preferred:
        s = find(preferred, sources)
        if s:
            return s, None
        d = default_source(sources)
        return d, "The selected source is not available; using the default input."
    return default_source(sources), None


# ---- input gain -------------------------------------------------------------------------------
# The gain is the source's own volume in PipeWire (what the desktop's sound settings call the input
# level), set with WirePlumber's wpctl. It is applied before any application reads the input, so
# the meter shows its effect at once, and it stays with the device for every program.
# wpctl takes node ids only; ids change when a device comes back, names do not.
GAIN_MAX = 1.5  # above 1.0 is PipeWire's software boost; past this it mostly adds noise and clipping


def node_id(name: str) -> int | None:
    try:
        dump = _pw_dump()
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    for o in dump:
        if o.get("type") == "PipeWire:Interface:Node" and ((o.get("info") or {}).get("props") or {}).get("node.name") == name:
            return o.get("id")
    return None


def parse_volume(out: str) -> float | None:
    """'Volume: 0.85' or 'Volume: 0.85 [MUTED]' (wpctl get-volume) -> 0.85."""
    m = re.match(r"\s*Volume:\s*([\d.]+)", out)
    return float(m.group(1)) if m else None


def get_volume(node: int) -> float | None:
    try:
        out = subprocess.run(["wpctl", "get-volume", str(node)], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_volume(out)


def set_volume(node: int, value: float) -> bool:
    value = max(0.0, min(GAIN_MAX, value))
    try:
        return subprocess.run(["wpctl", "set-volume", str(node), f"{value:.2f}"], capture_output=True,
                              timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _target_args(source: Source | None) -> list[str]:
    return ["--target", source.name] if source is not None and source.name else []


def _props(source: Source | None, role: str) -> str:
    # WirePlumber remembers where the user moved a stream by its application name and moves every
    # later stream of that name there. Moving Echo's microphone to a noise gate's source then
    # moved the computer-audio capture there too, and a call's two tracks became one: the
    # computer audio has a name of its own.
    app = "Echo"
    props = []
    if source is not None and source.kind == MONITOR:
        app, role = "Echo computer audio", f"{role}-computer"
        props.append("stream.capture.sink=true")
    props = [f'node.name="echo-{role}"', f'node.description="Echo {role}"',
             f'application.name="{app}"', 'media.role="Production"', *props]
    return "{ " + " ".join(props) + " }"


def record_cmd(source: Source | None, rate: int, channels: int, path: str) -> list[str]:
    """Raw s16 PCM capture to `path` ('-' for stdout)."""
    return ["pw-record", "--raw", *_target_args(source), "-P", _props(source, "recorder"),
            "--media-category", "Capture", "--rate", str(rate), "--channels", str(channels),
            "--format", "s16", "--latency", "20ms", path]


def monitor_cmd(source: Source | None, rate: int = 16000) -> list[str]:
    """Mono s16 stream to stdout for the level meter."""
    return ["pw-record", "--raw", *_target_args(source), "-P", _props(source, "meter"),
            "--media-category", "Capture", "--rate", str(rate), "--channels", "1",
            "--format", "s16", "--latency", "30ms", "-"]


def loopback_cmd(source: Source | None) -> list[str]:
    """Route the input to the default output so the user can hear it."""
    cmd = ["pw-loopback", "--latency", "30", "-n", "echo-listen"]
    if source is not None:
        cmd += ["-C", source.name]
        if source.kind == MONITOR:
            cmd += ["-i", "{ stream.capture.sink=true }"]
    return cmd
