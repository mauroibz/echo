"""Worker loop tests with a stub engine (no torch, no GPU)."""

import json
import subprocess
import threading
import time

import numpy as np
import pytest

from echo_app import importer
from echo_app.library import ERROR, PROGRESS, REQUESTED, TRANSCRIPT, Library
from echo_app.worker import service
from echo_app.worker.service import PARTIAL, Worker


class StubEngine:
    device = "stub"

    def __init__(self, fail=None, delay=0.0, on_batch=None):
        self.batch_size = 2
        self.loaded = False
        self.calls = []
        self.fail = fail
        self.delay = delay
        self.on_batch = on_batch
        self.vad_calls = 0

    def load(self):
        self.loaded = True

    def speech_regions(self, audio, progress=None):
        self.vad_calls += 1
        # Speech wherever the signal is loud, in 0.1 s frames.
        frame = 1600
        n = len(audio) // frame
        loud = np.abs(audio[: n * frame].reshape(n, frame)).max(axis=1) > 1000
        regions, start = [], None
        for i, on in enumerate(loud):
            if on and start is None:
                start = i / 10
            if not on and start is not None:
                regions.append((start, i / 10))
                start = None
        if start is not None:
            regions.append((start, n / 10))
        if progress:
            progress(1.0)
        return regions

    def transcribe(self, clips, adapter=True, context=None):
        if self.fail:
            raise self.fail
        self.calls.append([len(c) for c in clips])
        if self.on_batch:
            self.on_batch(len(self.calls))
        time.sleep(self.delay)
        return [f"texto {len(c) // 16000}s" for c in clips]

    def model_info(self, adapter):
        return {"base": "stub@1", "adapter": "stub-adapter@1" if adapter else None,
                "adapter_enabled": adapter, "device": "stub"}


def speechy_wav(path, pattern):
    """pattern: list of (seconds, loud?) building a 16 kHz WAV."""
    parts = []
    for sec, loud in pattern:
        n = int(sec * 16000)
        parts.append((np.sin(np.arange(n) * 0.1) * 8000).astype(np.int16) if loud else np.zeros(n, np.int16))
    data = np.concatenate(parts).tobytes()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", "pipe:0",
                    str(path)], input=data, check=True)
    return path


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "data")


def add(lib, tmp_path, name, pattern):
    src = speechy_wav(tmp_path / f"{name}.wav", pattern)
    return importer.import_file(lib, src).recording


def test_transcribes_with_times_paragraphs_and_provenance(lib, tmp_path):
    rec = add(lib, tmp_path, "a", [(1, False), (15, True), (3, False), (16, True), (1, False)])
    rec.request_transcription(adapter=True)
    eng = StubEngine()
    Worker(lib, eng).process(rec)
    t = rec.transcript()
    assert [round(s["start"]) for s in t["segments"]] == [1, 19]
    assert [s["paragraph"] for s in t["segments"]] == [True, True]  # 3 s pause
    assert t["text"] == "texto 15s\n\ntexto 16s"
    assert t["model"] == {"base": "stub@1", "adapter": "stub-adapter@1", "adapter_enabled": True}
    for name in (REQUESTED, PROGRESS, PARTIAL, ERROR):
        assert not rec.path(name).exists(), name


def test_crop_respected_and_times_absolute(lib, tmp_path):
    rec = add(lib, tmp_path, "c", [(5, True), (2, False), (5, True), (2, False), (5, True)])
    rec.update(crop_start=6.0, crop_end=13.0)
    rec.request_transcription()
    Worker(lib, StubEngine()).process(rec)
    segs = rec.transcript()["segments"]
    assert segs[0]["start"] >= 6.0 and segs[-1]["end"] <= 13.0
    assert len(segs) == 1 and segs[0]["start"] == pytest.approx(7.0, abs=0.15)


def test_queue_order_oldest_request_first(lib, tmp_path):
    a = add(lib, tmp_path, "a", [(3, True)])
    b = add(lib, tmp_path, "b", [(4, True)])
    b.request_transcription()
    time.sleep(0.01)
    a.request_transcription()
    assert [r.id for _, r in service.queued(lib)] == [b.id, a.id]


def test_resume_skips_done_passages(lib, tmp_path):
    pattern = []
    for _ in range(6):
        pattern += [(20, True), (1, False)]
    rec = add(lib, tmp_path, "long", pattern)
    rec.request_transcription()

    class Killed(BaseException):
        pass

    def die(n):
        if n == 2:
            raise Killed()

    eng = StubEngine(on_batch=die)
    with pytest.raises(Killed):
        Worker(lib, eng).process(rec)
    partial = json.loads(rec.path(PARTIAL).read_text())
    assert len(partial["results"]) == 2  # first batch saved before the "crash"
    eng2 = StubEngine()
    Worker(lib, eng2).process(rec)
    assert eng2.vad_calls == 0  # speech detection reused
    assert sum(len(c) for c in eng2.calls) == 4  # only the remaining passages
    assert len(rec.transcript()["segments"]) == 6


def test_partial_ignored_when_settings_change(lib, tmp_path):
    rec = add(lib, tmp_path, "p", [(10, True), (1, False), (10, True)])
    rec.request_transcription(adapter=True)
    (rec.path(PARTIAL)).write_text(json.dumps({"key": {"stale": True}, "regions": [[0, 1]], "results": {"0": "STALE"}}))
    eng = StubEngine()
    Worker(lib, eng).process(rec)
    assert eng.vad_calls == 1 and "STALE" not in rec.transcript()["text"]


def test_cancel_running_job_keeps_previous_transcript(lib, tmp_path):
    pattern = []
    for _ in range(8):
        pattern += [(20, True), (1, False)]
    rec = add(lib, tmp_path, "x", pattern)
    rec.path(TRANSCRIPT).write_text(json.dumps({"text": "anterior", "segments": []}))
    rec.request_transcription()
    eng = StubEngine(on_batch=lambda n: rec.cancel_transcription() if n == 1 else None)
    Worker(lib, eng).process(rec)
    assert rec.transcript()["text"] == "anterior"
    assert not rec.path(PROGRESS).exists() and not rec.path(PARTIAL).exists()
    assert len(eng.calls) == 1


def test_failure_reported_and_not_retried(lib, tmp_path):
    rec = add(lib, tmp_path, "f", [(5, True)])
    rec.request_transcription()
    Worker(lib, StubEngine(fail=RuntimeError("boom"))).process(rec)
    assert rec.transcript_status() == "failed" and rec.error_text() == "boom"
    assert service.queued(lib) == []


def test_models_missing_message(lib, tmp_path, monkeypatch):
    from echo_app import models
    from echo_app.worker import asr

    monkeypatch.setattr(models, "is_cached", lambda ref: False)
    rec = add(lib, tmp_path, "m", [(5, True)])
    rec.request_transcription()
    Worker(lib, asr.Engine()).process(rec)
    assert "echo-app models download" in rec.error_text()


def test_progress_file_while_running(lib, tmp_path):
    pattern = []
    for _ in range(6):
        pattern += [(20, True), (1, False)]
    rec = add(lib, tmp_path, "g", pattern)
    rec.request_transcription()
    seen = []
    eng = StubEngine(on_batch=lambda n: seen.append(json.loads(rec.path(PROGRESS).read_text())))
    Worker(lib, eng).process(rec)
    assert seen[0]["stage"] == "transcribing" and seen[-1]["done"] > seen[0]["done"]
    assert any(s["eta_s"] is not None for s in seen[1:])


def test_run_loop_processes_queue_then_exits_when_idle(lib, tmp_path):
    a = add(lib, tmp_path, "a", [(3, True)])
    b = add(lib, tmp_path, "b", [(3, True)])
    a.request_transcription()
    b.request_transcription()
    w = Worker(lib, StubEngine(), idle_seconds=0.5)
    t = threading.Thread(target=w.run)
    t.start()
    t.join(timeout=20)
    assert not t.is_alive()
    assert a.transcript_status() == "done" and b.transcript_status() == "done"


def test_single_worker_lock(lib):
    held = service.try_lock(lib)
    assert held is not None
    assert Worker(lib, StubEngine(), idle_seconds=0).run() == 0  # exits immediately
    held.close()


def test_worker_hands_over_to_another_folder(tmp_path):
    from echo_app import transcription

    a = Library(tmp_path / "a")
    b = Library(tmp_path / "b")
    w = Worker(a, StubEngine(), idle_seconds=60)
    t = threading.Thread(target=w.run)
    t.start()
    assert _wait(lambda: transcription.worker_info() is not None)
    assert transcription.worker_running(a) and not transcription.worker_running(b)
    # Pretend transcription is installed and spawning is a no-op: only the handover note matters.
    import echo_app.transcription as tr

    tr._wanted_path().write_text(str(b.data_dir))
    t.join(timeout=10)
    assert not t.is_alive(), "worker should hand over instead of idling for a minute"


def _wait(cond, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_oom_variants_are_recognized():
    from echo_app.worker.asr import is_oom

    class AcceleratorError(RuntimeError):
        pass

    assert is_oom(AcceleratorError("CUDA error: out of memory"))
    assert not is_oom(RuntimeError("shape mismatch"))
