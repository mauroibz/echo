"""The transcription worker loop. Engine-agnostic so it can be tested with a stub engine."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from ..audio import ffmpeg
from ..fsutil import atomic_write_json, flock_with_retry, read_json
from ..library import ERROR, PROGRESS, READY, REQUESTED, TRANSCRIPT, Library, Recording
from . import planning

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
PARTIAL = "transcript.partial.json"
POLL = 2.0


class EngineLike(Protocol):
    device: str
    batch_size: int

    def load(self) -> None: ...
    def speech_regions(self, audio: np.ndarray, progress=None) -> list[tuple[float, float]]: ...
    def transcribe(self, clips: list[np.ndarray], adapter: bool = True, context: str | None = None) -> list[str]: ...
    def model_info(self, adapter: bool) -> dict: ...


class Cancelled(Exception):
    pass


def try_lock(lib: Library):
    """One worker per user (the GPU holds one model), recording which folder it serves."""
    from .. import transcription

    f = flock_with_retry(transcription.lock_path())
    if f is None:
        return None
    f.seek(0)
    f.truncate()
    f.write(json.dumps({"pid": os.getpid(), "data_dir": str(lib.data_dir)}))
    f.flush()
    return f


def _other_folder_waiting(lib: Library) -> bool:
    from .. import transcription

    wanted = transcription.wanted_dir()
    return wanted is not None and wanted != str(lib.data_dir)


def queued(lib: Library) -> list[tuple[float, Recording]]:
    """Recordings with a transcription request, oldest request first."""
    jobs = []
    for rec in lib.all():
        marker = rec.path(REQUESTED)
        if not marker.exists() or rec.meta.state != READY or not rec.audio_path:
            continue
        try:
            ts = float(read_json(marker).get("requested", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            ts = marker.stat().st_mtime if marker.exists() else 0
        jobs.append((ts, rec))
    jobs.sort(key=lambda j: j[0])
    return jobs


def decode(rec: Recording) -> tuple[np.ndarray, float]:
    """16 kHz mono int16 samples of the crop span, and the offset of sample 0 in the recording."""
    start, end = rec.effective_span()
    r = subprocess.run(ffmpeg.decode_cmd(rec.audio_path, SAMPLE_RATE, 1, start or None, end),
                       capture_output=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"could not decode the audio: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.int16), float(start or 0.0)


def quietest_fn(audio: np.ndarray):
    frame = SAMPLE_RATE // 10

    def quietest(lo: float, hi: float) -> float:
        a, b = int(lo * SAMPLE_RATE), int(hi * SAMPLE_RATE)
        seg = audio[a:b].astype(np.float32)
        n = len(seg) // frame
        if n < 2:
            return hi
        rms = np.sqrt((seg[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
        return lo + float(np.argmin(rms)) * frame / SAMPLE_RATE

    return quietest


class Worker:
    def __init__(self, lib: Library, engine: EngineLike, idle_seconds: float = 300.0):
        self.lib = lib
        self.engine = engine
        self.idle_seconds = idle_seconds
        self._stop = False

    def _on_term(self, *_):
        self._stop = True

    def run(self) -> int:
        lock = try_lock(self.lib)
        if lock is None:
            log.info("another worker is running")
            return 0
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._on_term)
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        log.info("worker started (pid %d)", os.getpid())
        try:
            idle_since = time.monotonic()
            while not self._stop:
                jobs = queued(self.lib)
                if not jobs:
                    if time.monotonic() - idle_since > self.idle_seconds:
                        log.info("idle; exiting")
                        break
                    if _other_folder_waiting(self.lib):
                        log.info("another recordings folder has work; handing over")
                        break
                    time.sleep(POLL)
                    continue
                self.process(jobs[0][1])
                idle_since = time.monotonic()
        finally:
            lock.close()
        return 0

    # ---- one job ----
    def _progress(self, rec: Recording, stage: str, done: float, total: float, eta: float | None,
                  started: float) -> None:
        atomic_write_json(rec.path(PROGRESS), {"stage": stage, "done": round(done, 3), "total": round(total, 3),
                                               "eta_s": None if eta is None else round(eta), "started": started,
                                               "updated": time.time()})

    @staticmethod
    def _request(rec: Recording) -> dict[str, Any] | None:
        try:
            return read_json(rec.path(REQUESTED))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _check(self, rec: Recording, requested_at) -> None:
        req = self._request(rec)
        if req is None or req.get("requested") != requested_at or self._stop:
            raise Cancelled()

    def process(self, rec: Recording) -> None:
        req = self._request(rec) or {}
        requested_at = req.get("requested")
        adapter = bool(req.get("adapter", True))
        context = req.get("context") or None
        started = time.time()
        try:
            self._progress(rec, "loading", 0, 1, None, started)
            self.engine.load()
            self._check(rec, requested_at)
            self._transcribe(rec, requested_at, adapter, context, started)
        except Cancelled:
            log.info("%s: cancelled", rec.id)
            if self._request(rec) is None:
                rec.path(PARTIAL).unlink(missing_ok=True)
            rec.path(PROGRESS).unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001 - every failure is reported on the recording
            log.exception("%s: transcription failed", rec.id)
            msg = str(e) or e.__class__.__name__
            if "out of memory" in msg.lower() and "GPU memory" not in msg:
                from .asr import OOM_MESSAGE

                msg = OOM_MESSAGE
            rec.path(ERROR).write_text(msg + "\n", encoding="utf-8")
            rec.path(REQUESTED).unlink(missing_ok=True)
            rec.path(PROGRESS).unlink(missing_ok=True)

    def _transcribe(self, rec: Recording, requested_at, adapter: bool, context: str | None, started: float) -> None:
        audio, offset = decode(rec)
        total_s = len(audio) / SAMPLE_RATE
        info = self.engine.model_info(adapter)
        key = {"audio": rec.meta.sha256, "crop": [rec.meta.crop_start, rec.meta.crop_end],
               "model": info.get("base"), "adapter": info.get("adapter"), "context": context,
               "style": info.get("style_context")}
        partial = self._load_partial(rec, key)
        if partial.get("regions") is None:
            last = [0.0]

            def vad_progress(frac: float):
                now = time.monotonic()
                if now - last[0] > 1.0:
                    last[0] = now
                    self._check(rec, requested_at)
                    self._progress(rec, "detecting", frac, 1.0, None, started)

            self._progress(rec, "detecting", 0, 1, None, started)
            partial["regions"] = self.engine.speech_regions(audio, vad_progress)
            partial["results"] = {}
            atomic_write_json(rec.path(PARTIAL), partial)
        passages = planning.plan(partial["regions"], quietest_fn(audio))
        results: dict[str, str] = partial.setdefault("results", {})
        todo = [i for i in range(len(passages)) if str(i) not in results]
        # Longest first keeps batches uniform in length.
        todo.sort(key=lambda i: passages[i].duration, reverse=True)
        speech_total = sum(p.duration for p in passages) or 1.0
        done_s = sum(passages[int(i)].duration for i in results if int(i) < len(passages))
        t0, processed = time.monotonic(), 0.0
        self._progress(rec, "transcribing", done_s, speech_total, None, started)
        pos = 0
        while pos < len(todo):
            self._check(rec, requested_at)
            batch = todo[pos:pos + max(1, self.engine.batch_size)]
            clips = [audio[int(passages[i].start * SAMPLE_RATE):int(passages[i].end * SAMPLE_RATE)] for i in batch]
            texts = self.engine.transcribe(clips, adapter=adapter, context=context)
            for i, text in zip(batch, texts):
                results[str(i)] = text
            atomic_write_json(rec.path(PARTIAL), partial)
            pos += len(batch)
            seconds = sum(passages[i].duration for i in batch)
            done_s += seconds
            processed += seconds
            rate = processed / max(1e-6, time.monotonic() - t0)
            eta = (speech_total - done_s) / rate if rate > 0 else None
            self._progress(rec, "transcribing", done_s, speech_total, eta, started)
        self._check(rec, requested_at)
        segments = [{"start": round(p.start + offset, 2), "end": round(p.end + offset, 2),
                     "text": results.get(str(i), ""), "paragraph": p.paragraph}
                    for i, p in enumerate(passages)]
        transcript = {
            "version": 1, "language": "es",
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": {k: info.get(k) for k in ("base", "adapter", "adapter_enabled")},
            "device": info.get("device"), "audio_sha256": rec.meta.sha256,
            "crop": [rec.meta.crop_start, rec.meta.crop_end], "duration": round(total_s, 2),
            "segments": segments, "text": planning.join_text(segments),
            "elapsed_s": round(time.time() - started, 1),
        }
        if context:
            transcript["context"] = context
        atomic_write_json(rec.path(TRANSCRIPT), transcript)
        # Only now is the job complete; a re-request in the meantime keeps its marker.
        if (self._request(rec) or {}).get("requested") == requested_at:
            rec.path(REQUESTED).unlink(missing_ok=True)
        for name in (PROGRESS, PARTIAL, ERROR):
            rec.path(name).unlink(missing_ok=True)
        log.info("%s: transcribed %.0f s of audio in %.0f s", rec.id, total_s, time.time() - started)

    @staticmethod
    def _load_partial(rec: Recording, key: dict) -> dict:
        try:
            p = read_json(rec.path(PARTIAL))
            if p.get("key") == key:
                log.info("%s: resuming with %d passages done", rec.id, len(p.get("results", {})))
                return p
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {"key": key, "regions": None, "results": {}}


def main(data_dir: str, idle_minutes: float | None = None) -> int:
    from ..settings import load
    from .asr import Engine

    cfg, _ = load()
    idle = (idle_minutes if idle_minutes is not None else cfg.worker_idle_minutes) * 60
    lib = Library(Path(data_dir))
    return Worker(lib, Engine(), idle_seconds=idle).run()
