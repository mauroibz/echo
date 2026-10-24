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


def _target_args(source: Source | None) -> list[str]:
    return ["--target", source.name] if source is not None else []


def _props(source: Source | None, role: str) -> str:
    props = [f'node.name="echo-{role}"', f'node.description="Echo {role}"',
             'application.name="Echo"', 'media.role="Production"']
    if source is not None and source.kind == MONITOR:
        props.append("stream.capture.sink=true")
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
