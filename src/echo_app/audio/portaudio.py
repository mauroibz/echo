"""The PortAudio backend, through sounddevice: Windows, macOS, and Linux without PipeWire.

Capture runs inside the supervisor process: a callback hands blocks to a writer thread that
appends them to the take, and the supervisor's loop fsyncs the take every two seconds as it does
for pw-record. A crash of the supervisor therefore loses at most the unflushed seconds, the
same bound the design accepts for a power cut; there is no separate capture process to adopt.

Sources are named "pa:<host API>:<device name>": device indexes change when devices come and go,
names do not, and the prefix keeps a saved PipeWire choice from being misread here.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
from pathlib import Path

from .pipewire import INPUT, Source

log = logging.getLogger(__name__)

PREFIX = "pa:"
# One host API per platform, so each device is listed once (Windows offers MME, DirectSound,
# WASAPI and WDM-KS views of the same microphone).
PREFERRED_API = {"win32": "Windows WASAPI", "darwin": "Core Audio", "linux": "ALSA"}


def _sd():
    import sounddevice

    return sounddevice


def available() -> bool:
    """sounddevice imports and PortAudio is loadable (on Linux it is a system library)."""
    try:
        _sd()
        return True
    except (ImportError, OSError):
        return False


class PortAudioCapture:
    """An input stream writing raw s16 PCM to a take."""

    def __init__(self, device: int | None, rate: int, channels: int, path: Path, log_file):
        sd = _sd()
        self.pid = None
        self.path = Path(path)
        self.channels = channels
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._file = open(self.path, "ab", buffering=0)
        self._error: str | None = None
        # Its own handle on the take's log: the caller closes the one it passed once we are running.
        self._log = open(self.path.with_suffix(".log"), "ab")
        try:
            self.rate = rate
            self._stream = sd.RawInputStream(samplerate=rate, channels=channels, dtype="int16", device=device,
                                             callback=self._callback, blocksize=0)
        except sd.PortAudioError:
            # Shared-mode devices (WASAPI) accept only their own rate: record at that rate, and the
            # session follows it (see Supervisor._start_take).
            info = sd.query_devices(device, "input")
            self.rate = int(info["default_samplerate"])
            self._stream = sd.RawInputStream(samplerate=self.rate, channels=channels, dtype="int16", device=device,
                                             callback=self._callback, blocksize=0)
        self._writer = threading.Thread(target=self._write, daemon=True)
        self._writer.start()
        self._stream.start()

    def _callback(self, data, _frames, _time, status):
        if status and status.input_overflow:
            self._note("input overflow")
        self._queue.put(bytes(data))

    def _note(self, text: str):
        try:
            self._log.write(f"{text}\n".encode())
        except (OSError, ValueError):
            pass

    def _write(self):
        while True:
            block = self._queue.get()
            if block is None:
                return
            try:
                self._file.write(block)
            except OSError as e:
                self._error = str(e)
                return

    def alive(self) -> bool:
        return self._error is None and self._stream.active

    def stop(self, timeout: float = 3.0) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:  # noqa: BLE001 - the device may already be gone
            log.warning("closing the input stream: %s", e)
        self._queue.put(None)
        self._writer.join(timeout)
        try:
            os.fsync(self._file.fileno())
        except OSError:
            pass
        self._file.close()
        self._log.close()


class PortAudioStream:
    """Mono s16 for the level meter, at the device's own rate (a peak needs no particular rate)."""

    def __init__(self, device: int | None):
        sd = _sd()
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._buf = b""
        info = sd.query_devices(device, "input")
        self._stream = sd.RawInputStream(samplerate=int(info["default_samplerate"]), channels=1, dtype="int16",
                                         device=device, callback=self._callback)
        self._stream.start()

    def _callback(self, data, _frames, _time, _status):
        try:
            self._queue.put_nowait(bytes(data))
        except queue.Full:
            pass  # the meter only needs the latest audio

    def read(self, n: int) -> bytes:
        while len(self._buf) < n and self.running():
            try:
                self._buf += self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def running(self) -> bool:
        return self._stream.active

    def stop(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001
            pass


class PortAudioOutput:
    """Plays raw s16 from a pipe (ffmpeg's stdout); looks like a process to the player."""

    CHUNK = 4096

    def __init__(self, rate: int, channels: int, stdin):
        sd = _sd()
        self._pipe = stdin
        self._stop = threading.Event()
        self._stream = sd.RawOutputStream(samplerate=rate, channels=channels, dtype="int16", latency="low")
        self._stream.start()
        self._thread = threading.Thread(target=self._pump, args=(channels,), daemon=True)
        self._thread.start()

    def _pump(self, channels: int):
        frame = 2 * channels
        rest = b""
        try:
            while not self._stop.is_set():
                data = self._pipe.read(self.CHUNK)
                if not data:
                    break
                data = rest + data
                usable = len(data) - len(data) % frame
                rest = data[usable:]
                self._stream.write(data[:usable])
        except (OSError, ValueError):
            pass
        finally:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass

    def poll(self) -> int | None:
        return None if self._thread.is_alive() else 0

    def terminate(self) -> None:
        self._stop.set()
        try:
            self._stream.abort()
        except Exception:  # noqa: BLE001
            pass

    def wait(self, timeout: float | None = None) -> int:
        self._thread.join(timeout)
        try:
            self._pipe.close()
        except OSError:
            pass
        return 0


class PortAudioBackend:
    name = "portaudio"
    records_outputs = False  # "Computer audio" on Windows needs WASAPI loopback: a later change
    can_listen = False

    def _api_index(self) -> int | None:
        sd = _sd()
        want = PREFERRED_API.get(sys.platform)
        for i, api in enumerate(sd.query_hostapis()):
            if api["name"] == want:
                return i
        return None

    def list_sources(self) -> list[Source]:
        sd = _sd()
        api = self._api_index()
        try:
            default_in = sd.default.device[0]
        except Exception:  # noqa: BLE001
            default_in = -1
        out = []
        apis = sd.query_hostapis()
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] <= 0 or (api is not None and d["hostapi"] != api):
                continue
            name = f"{PREFIX}{apis[d['hostapi']]['name']}:{d['name']}"
            out.append(Source(name, d["name"], INPUT, d["max_input_channels"], i == default_in))
        out.sort(key=lambda s: (not s.is_default, s.description.lower()))
        if out and not any(s.is_default for s in out):
            first = out[0]
            out[0] = Source(first.name, first.description, INPUT, first.channels, True)
        return out

    def default_source(self, sources=None):
        sources = self.list_sources() if sources is None else sources
        return next((s for s in sources if s.is_default), sources[0] if sources else None)

    def find(self, name, sources=None):
        sources = self.list_sources() if sources is None else sources
        return next((s for s in sources if s.name == name), None)

    def resolve(self, preferred, sources=None):
        sources = self.list_sources() if sources is None else sources
        if preferred:
            s = self.find(preferred, sources)
            if s:
                return s, None
            return self.default_source(sources), "The selected source is not available; using the default input."
        return self.default_source(sources), None

    def _device(self, source: Source | None) -> int | None:
        """The current device index for a source (indexes move as devices come and go)."""
        if source is None:
            return None
        sd = _sd()
        apis = sd.query_hostapis()
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and f"{PREFIX}{apis[d['hostapi']]['name']}:{d['name']}" == source.name:
                return i
        return None

    def start_capture(self, source, rate, channels, path, log_file) -> PortAudioCapture:
        return PortAudioCapture(self._device(source), rate, channels, path, log_file)

    def meter(self, source, rate) -> PortAudioStream:
        return PortAudioStream(self._device(source))

    def output(self, rate, channels, stdin) -> PortAudioOutput:
        return PortAudioOutput(rate, channels, stdin)

    def listen(self, source):
        return None
