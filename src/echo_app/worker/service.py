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

from .. import models
from ..audio import ffmpeg
from .. import locks
from ..fsutil import atomic_write_json, read_json
from ..library import ERROR, PROGRESS, READY, RELABELED, REQUESTED, TRANSCRIPT, VOICEPRINTS, Library, Recording
from . import planning

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
PARTIAL = "transcript.partial.json"
POLL = 2.0
LOW_SD = 1.5  # a passage this many standard deviations below the recording's mean log-probability is "low"
LOW_MIN_PASSAGES = 5  # fewer passages give no meaningful spread
# What the model answers for a fragment it cannot make out, said as confidently as real words (its
# log-probability does not tell them apart). Passages this short only come from cutting out
# interruptions; in one real meeting 21 of 96 such pieces came back as "Gracias.", against none
# before the cuts, and padding them with silence only traded it for other inventions.
HALLUCINATED = {"es": ("gracias",)}
HALLUCINATED_BELOW = 1.5  # seconds


class EngineLike(Protocol):
    device: str
    batch_size: int

    def load(self) -> None: ...
    def speech_regions(self, audio: np.ndarray, progress=None) -> list[tuple[float, float]]: ...
    def transcribe(self, clips: list[np.ndarray], adapter: bool = True, context: str | None = None,
                   language: str = "es") -> list[str]: ...
    def model_info(self, adapter: bool, language: str = "es") -> dict: ...


class Cancelled(Exception):
    pass


def try_lock(lib: Library):
    """One worker per user (the GPU holds one model), recording which folder it serves."""
    from .. import transcription

    lock = locks.acquire(transcription.lock_path(), wait=2.0)
    if lock is None:
        return None
    lock.write_payload(json.dumps({"pid": os.getpid(), "data_dir": str(lib.data_dir)}))
    return lock


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
    cmd = ffmpeg.decode_cmd(rec.audio_path, SAMPLE_RATE, 1, start or None, end, mix=bool(rec.meta.tracks))
    r = subprocess.run(cmd, capture_output=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"could not decode the audio: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.int16), float(start or 0.0)


TRACKS_RATE = 4000  # enough to tell which side is louder: an hour is 57 MB instead of 230 at 16 kHz


def decode_tracks(rec: Recording) -> np.ndarray:
    """A call recording's crop span as (N, 2) samples at TRACKS_RATE: the microphone, the computer audio."""
    start, end = rec.effective_span()
    r = subprocess.run(ffmpeg.decode_cmd(rec.audio_path, TRACKS_RATE, 2, start or None, end),
                       capture_output=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"could not decode the audio: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.int16).reshape(-1, 2)


def decode_track(rec: Recording, track: int) -> np.ndarray:
    """One track of a call's crop span alone, 16 kHz mono int16 (1 the computer audio)."""
    start, end = rec.effective_span()
    r = subprocess.run(ffmpeg.decode_cmd(rec.audio_path, SAMPLE_RATE, 1, start or None, end, track=track),
                       capture_output=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"could not decode the audio: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.int16)


def _speaker_tracks(labels, sides, spans) -> dict[str, int]:
    """Each speaker's track in a call (0 the microphone, 1 the computer audio): where most of their speech is."""
    secs: dict[int, list[float]] = {}
    for who, side, (start, end) in zip(labels, sides, spans):
        if who is not None:
            secs.setdefault(who, [0.0, 0.0])[side] += end - start
    return {str(n): int(s[1] > s[0]) for n, s in secs.items()}


def name_user(rec: Recording, record: dict) -> int | None:
    """Name the user in `rec`, given its speakers record; returns their speaker number.

    In a call, the one speaker on the microphone track is the user: the track says so, and their
    voice is learned from it. Otherwise it is the speaker whose voice was suggested as the user's;
    that match is not folded back into the voice, so one wrong match cannot drift it. A name the
    user gave is never replaced, and nobody else is named here: other people are confirmed by the
    user (see docs/design.md).
    """
    from .. import dictionary, settings

    name = settings.load()[0].your_name.strip()
    if not name:
        return None
    named = dict(rec.reload().meta.speakers)
    for n, given in named.items():
        if given == name:
            return int(n)
    mic = [n for n, t in (record.get("tracks") or {}).items() if t == 0]
    certain = len(mic) == 1
    n = mic[0] if certain else next((k for k, v in (record.get("suggested") or {}).items() if v == name), None)
    if n is None or n in named:
        return None
    rec.update(speakers={**named, n: name})
    centroid = (record.get("centroids") or {}).get(n)
    if certain and centroid:
        dictionary.remember_voice(name, centroid, rec.id)
    log.info("%s: speaker %s is the user", rec.id, n)
    return int(n)


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


def _fold(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()


def mark_low(segments: list[dict]) -> None:
    """Flag passages the model was unusually unsure of, relative to the rest of this recording:
    fixed thresholds do not carry over between microphones and speakers."""
    lps = [s["logprob"] for s in segments if s.get("logprob") is not None and s.get("text")]
    if len(lps) < LOW_MIN_PASSAGES:
        return
    mean = sum(lps) / len(lps)
    sd = (sum((x - mean) ** 2 for x in lps) / len(lps)) ** 0.5
    for s in segments:
        lp = s.get("logprob")
        if lp is not None and s.get("text") and sd > 0 and lp < mean - LOW_SD * sd and "low" not in s["flags"]:
            s["flags"].append("low")


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
        language = req.get("language") or "es"
        adapter = bool(req.get("adapter", True)) and language == "es"  # the adapter is Spanish only
        context = req.get("context") or None
        started = time.time()
        self._stereo = None  # a call's tracks, decoded once per job (the crop may have changed)
        try:
            self._progress(rec, "loading", 0, 1, None, started)
            self.engine.load()
            self._check(rec, requested_at)
            self._transcribe(rec, requested_at, adapter, context, started, language)
        except Cancelled:
            log.info("%s: cancelled", rec.id)
            try:
                if self._request(rec) is None:
                    rec.path(PARTIAL).unlink(missing_ok=True)
                rec.path(PROGRESS).unlink(missing_ok=True)
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001 - every failure is reported on the recording
            log.exception("%s: transcription failed", rec.id)
            msg = str(e) or e.__class__.__name__
            if "out of memory" in msg.lower() and "GPU memory" not in msg:
                from .asr import OOM_MESSAGE

                msg = OOM_MESSAGE
            if not rec.folder.exists():
                return  # deleted while being transcribed
            try:
                rec.path(ERROR).write_text(msg + "\n", encoding="utf-8")
                rec.path(REQUESTED).unlink(missing_ok=True)
                rec.path(PROGRESS).unlink(missing_ok=True)
            except OSError:
                log.exception("%s: could not record the failure", rec.id)

    def _transcribe(self, rec: Recording, requested_at, adapter: bool, context: str | None, started: float,
                    language: str = "es") -> None:
        audio, offset = decode(rec)
        total_s = len(audio) / SAMPLE_RATE
        info = self.engine.model_info(adapter, language)
        key = {"audio": rec.meta.sha256, "crop": [rec.meta.crop_start, rec.meta.crop_end],
               "model": info.get("base"), "adapter": info.get("adapter"), "context": context,
               "style": info.get("style_context"), "language": language}
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
        quietest = quietest_fn(audio)
        passages = planning.plan(partial["regions"], quietest)
        if "turns" not in partial:
            # A job resumed from before interruptions were found was planned without cuts; its
            # results are numbered by those passages, so it stays that way.
            partial["turns"] = [] if partial.get("results") else \
                self._turns(rec, requested_at, passages, audio, started)
            atomic_write_json(rec.path(PARTIAL), partial)
        passages = planning.cut(passages, partial["turns"], quietest)
        results: dict[str, dict | str] = partial.setdefault("results", {})
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
            if hasattr(self.engine, "transcribe_flagged"):
                out = self.engine.transcribe_flagged(clips, adapter=adapter, context=context, language=language)
            else:
                out = [(t, [], None) for t in self.engine.transcribe(clips, adapter=adapter, context=context,
                                                                     language=language)]
            for i, (text, flags, logprob) in zip(batch, out):
                results[str(i)] = {"text": text, "flags": flags, "logprob": logprob}
            atomic_write_json(rec.path(PARTIAL), partial)
            pos += len(batch)
            seconds = sum(passages[i].duration for i in batch)
            done_s += seconds
            processed += seconds
            rate = processed / max(1e-6, time.monotonic() - t0)
            eta = (speech_total - done_s) / rate if rate > 0 else None
            self._progress(rec, "transcribing", done_s, speech_total, eta, started)
        self._check(rec, requested_at)
        segments = []
        for i, p in enumerate(passages):
            r = results.get(str(i), "")
            r = r if isinstance(r, dict) else {"text": r}  # partial files from before the flags
            seg = {"start": round(p.start + offset, 2), "end": round(p.end + offset, 2), "text": r.get("text", ""),
                   "paragraph": p.paragraph, "flags": list(r.get("flags") or [])}
            if p.duration < HALLUCINATED_BELOW and _fold(seg["text"]) in HALLUCINATED.get(language, ()):
                seg["dropped"], seg["text"] = seg["text"], ""  # kept for the record, not shown
            if r.get("logprob") is not None:
                seg["logprob"] = r["logprob"]
            segments.append(seg)
        mark_low(segments)
        who, prints = self._speakers(rec, requested_at, passages, audio, segments, started) or (None, None)
        transcript = {
            "version": 2, "language": language,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": {k: info.get(k) for k in ("base", "adapter", "adapter_enabled")},
            "device": info.get("device"), "audio_sha256": rec.meta.sha256,
            "crop": [rec.meta.crop_start, rec.meta.crop_end], "duration": round(total_s, 2),
            "segments": segments, "text": planning.join_text(segments, language),
            "elapsed_s": round(time.time() - started, 1),
        }
        if context:
            transcript["context"] = context
        if who:
            transcript["speakers"] = who
        if prints:
            prints["transcript"] = transcript["created"]
            atomic_write_json(rec.path(VOICEPRINTS), prints)
        else:
            rec.path(VOICEPRINTS).unlink(missing_ok=True)
        atomic_write_json(rec.path(TRANSCRIPT), transcript)
        rec.path(RELABELED).unlink(missing_ok=True)  # it was for the labels just replaced
        if rec.meta.title_auto:
            from ..library import auto_title

            rec.reload()
            title = auto_title(rec.text())
            if title and rec.meta.title_auto:
                rec.update(title=title)
        try:
            from .. import sets
            from ..library import Library

            library = Library(rec.folder.parent.parent)
            sets.refresh_title(library, sets.set_of(library, rec.id))  # a set titled by its first part
        except Exception:  # noqa: BLE001 - a set file problem must not fail the transcription
            log.exception("%s: set title not updated", rec.id)
        try:
            from .. import dictionary

            dictionary.apply(rec)  # known aliases fixed in the copy the user sees
        except Exception:  # noqa: BLE001 - a dictionary problem must not fail the transcription
            log.exception("%s: dictionary correction failed", rec.id)
        # Only now is the job complete; a re-request in the meantime keeps its marker.
        if (self._request(rec) or {}).get("requested") == requested_at:
            rec.path(REQUESTED).unlink(missing_ok=True)
        for name in (PROGRESS, PARTIAL, ERROR):
            rec.path(name).unlink(missing_ok=True)
        if not partial.get("resumed"):  # a resumed job's time would overstate the speed
            from .. import transcription

            transcription.record_speed(transcription.speed_key(info.get("device", "cpu")), total_s,
                                       time.time() - started)
        log.info("%s: transcribed %.0f s of audio in %.0f s", rec.id, total_s, time.time() - started)

    def _labels_speakers(self, rec: Recording) -> bool:
        return not rec.meta.speakers_off and getattr(self.engine, "labels_speakers", True)

    def _call_tracks(self, rec: Recording) -> np.ndarray | None:
        """A call's two tracks at TRACKS_RATE, or None for one source, or for a call whose tracks
        are one sound recorded twice: it is then labeled like a single microphone."""
        if not rec.meta.tracks:
            return None
        cached = getattr(self, "_stereo", None)
        if cached is None or cached[0] != rec.id:
            from . import speakers

            stereo = decode_tracks(rec)
            if not speakers.tracks_differ(stereo, TRACKS_RATE):
                log.warning("%s: both tracks hold the same sound; labeled as one microphone", rec.id)
                stereo = None
            cached = self._stereo = (rec.id, stereo)
        return cached[1]

    def _turns(self, rec: Recording, requested_at, passages, audio, started) -> list[list[float]]:
        """Spans where someone interrupts a passage's main voice, found before recognition so
        that each becomes a passage of its own (speakers.interruptions). None without both
        speaker models or for recordings marked as monologues."""
        if not self._labels_speakers(rec):
            return []
        from . import speakers

        if not (speakers.Segmenter.available() and speakers.Embedder.available()):
            return []
        seg = getattr(self, "_segmenter", None) or speakers.Segmenter()
        self._segmenter = seg
        # A call: the change of side is where the other track speaks, and segmentation listens to
        # the computer audio alone, where everyone but the user is. On the mix it found pauses
        # full of "people" (pieces the model heard as "Gracias.") and missed half of what was
        # said over someone.
        stereo = self._call_tracks(rec)
        source = decode_track(rec, 1) if stereo is not None else audio
        spans: list[list[float]] = []
        last = 0.0
        for i, p in enumerate(passages):
            clip = source[int(p.start * SAMPLE_RATE):int(p.end * SAMPLE_RATE)]
            least = speakers.MIN_TURN if stereo is None else speakers.CALL_MIN_TURN
            found = speakers.interruptions(speakers.local_activity(seg.window, clip), p.start, least)
            if stereo is not None:
                sides = speakers.track_turns(stereo, TRACKS_RATE, p.start, p.end, least)
                found = speakers.split_spans(sides + found)
            for s, e in found:
                spans.append([round(s, 3), round(e, 3)])
            if time.monotonic() - last > 1.0:
                last = time.monotonic()
                self._check(rec, requested_at)
                self._progress(rec, "speakers", i, len(passages), None, started)
        log.info("%s: %d interruptions cut out of %d passages", rec.id, len(spans), len(passages))
        return spans

    def _speakers(self, rec: Recording, requested_at, passages, audio, segments,
                  started) -> tuple[dict, dict] | None:
        """Label passages by speaker (a separate stage after recognition, on the processor).

        Sets `speaker` on each segment and returns the transcript's `speakers` record: the count,
        each speaker's voice centroid (for naming and for recognizing them later) and names
        suggested from voices the user named before; and the passages' voiceprints, which let
        the window reassign passages from the user's fixes (relabel.py). Skipped without the
        speaker model, for recordings marked as monologues, and for engines that do not provide
        it (tests).
        """
        if not self._labels_speakers(rec):
            return None
        from . import speakers

        if not speakers.Embedder.available():
            log.info("%s: no speaker model; passages are not labeled by speaker", rec.id)
            return None
        emb = getattr(self, "_embedder", None) or speakers.Embedder()
        self._embedder = emb
        embs, glimpses = {}, {}
        last = 0.0
        for i, p in enumerate(passages):
            if not segments[i].get("text"):
                pass
            elif p.duration >= speakers.MIN_SECONDS:
                embs[i] = emb.embed(audio[int(p.start * SAMPLE_RATE):int(p.end * SAMPLE_RATE)])
            elif p.interrupting and p.duration >= speakers.MIN_GLIMPSE:
                glimpses[i] = emb.embed(audio[int(p.start * SAMPLE_RATE):int(p.end * SAMPLE_RATE)])
            if time.monotonic() - last > 1.0:
                last = time.monotonic()
                self._check(rec, requested_at)
                self._progress(rec, "speakers", i, len(passages), None, started)
        spans = [(p.start, p.end) for p in passages]
        interrupting = [p.interrupting for p in passages] if any(p.interrupting for p in passages) else None
        sides = None
        stereo = self._call_tracks(rec)
        if stereo is not None:
            sides = speakers.louder_track(stereo, spans, TRACKS_RATE)
            if interrupting:
                sides = speakers.interrupting_sides(stereo, TRACKS_RATE, spans, sides, interrupting)
        labels, centroids = speakers.label(spans, embs, tracks=sides, interrupting=interrupting,
                                           glimpses=glimpses)
        tracks = _speaker_tracks(labels, sides, spans) if sides is not None else None
        if not centroids:
            return None
        prev = None
        for seg, who in zip(segments, labels):
            seg["speaker"] = who
            if seg.get("text"):
                if prev is not None and who != prev:
                    seg["paragraph"] = True  # a new speaker starts a new paragraph
                prev = who
        from .. import dictionary

        suggestions = {}
        for n, c in centroids.items():
            best = dictionary.recognize(c, speakers.similarity, speakers.RECOGNIZE)
            if best:
                suggestions[str(n)] = best
        record = {"count": len(centroids), "centroids": {str(k): v for k, v in centroids.items()},
                  "suggested": suggestions, "model": f"{models.SPEAKER.repo}@{models.SPEAKER.revision}"}
        if tracks is not None:
            record["tracks"] = tracks
        if rec.reload().meta.speaker_merges:
            rec.update(speaker_merges={})  # new labels are numbered afresh: old merges would join strangers
        me = name_user(rec, record)
        if me is not None:
            record["me"] = me
        voiced = sorted({**embs, **glimpses}.items())
        prints = {"passages": {str(k): [round(float(x), 4) for x in v] for k, v in voiced},
                  "interrupting": [i for i, p in enumerate(passages) if p.interrupting]}
        return record, prints

    @staticmethod
    def _load_partial(rec: Recording, key: dict) -> dict:
        try:
            p = read_json(rec.path(PARTIAL))
            if p.get("key") == key:
                log.info("%s: resuming with %d passages done", rec.id, len(p.get("results", {})))
                p["resumed"] = True
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
