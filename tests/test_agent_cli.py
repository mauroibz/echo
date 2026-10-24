"""The scripted command line: files in, transcripts out, safe to repeat, JSON, exit codes, headless."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from echo_app import cli, cli_json, features, models, settings, transcription
from echo_app.library import REQUESTED, TRANSCRIPT, Library
from echo_app.worker.service import Worker
from test_video_import import make_video
from test_worker import StubEngine, speechy_wav

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture
def lib(monkeypatch):
    monkeypatch.setattr(features, "transcription_installed", lambda: True)
    monkeypatch.setattr(models, "all_cached", lambda: True)
    return Library(settings.load()[0].data_path)


class FakeWorker:
    """Runs queued jobs with the stub engine in a thread, as the detached worker would."""

    def __init__(self, lib, engine=None):
        self.lib, self.engine = lib, engine or StubEngine()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop.wait(0.05):
            for rec in self.lib.all():
                if rec.path(REQUESTED).exists():
                    Worker(self.lib, self.engine).process(rec)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(5)


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def speech(tmp_path, name="meeting.wav"):
    return speechy_wav(tmp_path / name, [(1, False), (6, True), (2, False), (5, True), (1, False)])


def test_file_to_markdown_on_stdout(lib, tmp_path, capsys):
    f = speech(tmp_path)
    with FakeWorker(lib):
        code, out, err = run(capsys, "transcribe", str(f), "--format", "md", "--timeout", "60")
    assert code == 0, err
    assert out.startswith("# meeting\n") and "texto 13s" in out  # the stub engine's text
    assert "texto" not in err and "Imported meeting.wav" in err  # notes go to stderr, never stdout
    (rec,) = lib.all()
    assert rec.transcript_status() == "done"


def test_video_input(lib, tmp_path, capsys):
    v = make_video(tmp_path / "2026-09-23 15-02-29.mp4", ["-c:a", "aac"], seconds=3)
    with FakeWorker(lib):
        code, out, err = run(capsys, "transcribe", str(v), "--format", "txt", "--timeout", "60")
    assert code == 0, err
    assert out.strip().startswith("texto")
    assert lib.all()[0].meta.extracted_from["method"] == "copy"


def test_rerun_imports_and_queues_nothing(lib, tmp_path, capsys, monkeypatch):
    f = speech(tmp_path)
    with FakeWorker(lib):
        first = run(capsys, "transcribe", str(f), "--format", "md", "--timeout", "60")
    monkeypatch.setattr(transcription, "request", lambda *a, **k: pytest.fail("queued again"))
    second = run(capsys, "transcribe", str(f), "--format", "md")
    assert first[0] == second[0] == 0 and first[1] == second[1]
    assert "Already transcribed" in second[2]
    assert len(lib.all()) == 1


def test_again_queues_a_new_run(lib, tmp_path, capsys):
    f = speech(tmp_path)
    with FakeWorker(lib):
        run(capsys, "transcribe", str(f), "--wait", "--timeout", "60")
    rid = lib.all()[0].id
    code, out, _ = run(capsys, "transcribe", rid, "--again")
    assert code == 0 and f"Queued {rid}" in out
    assert lib.get(rid).path(REQUESTED).exists()


def test_missing_input_queues_nothing(lib, tmp_path, capsys):
    f = speech(tmp_path)
    code, out, err = run(capsys, "transcribe", str(f), str(tmp_path / "nope.mp4"))
    assert code == 1 and "No recording or file" in err and "nope.mp4" in err
    assert lib.all() == []  # nothing imported either


@pytest.mark.parametrize("argv,message", [
    (["a.wav", "b.wav", "--format", "md"], "--out FOLDER"),
    (["a.wav", "--format", "md", "--json"], "--json and --format"),
    ([], "Give recording ids"),
])
def test_usage_errors(lib, tmp_path, capsys, argv, message):
    for name in ("a.wav", "b.wav"):
        speech(tmp_path, name)
    os.chdir(tmp_path)
    code, out, err = run(capsys, "transcribe", *argv)
    assert code == 2 and message in err and out == ""
    assert lib.all() == []


def test_timeout_leaves_the_job_and_rerun_finishes(lib, tmp_path, capsys):
    f = speech(tmp_path)
    code, out, err = run(capsys, "transcribe", str(f), "--format", "md", "--timeout", "0.3")
    assert code == 3 and out == ""
    assert "run the same command again" in err
    (rec,) = lib.all()
    assert rec.transcript_status() == "queued"  # not cancelled
    with FakeWorker(lib):
        code, out, err = run(capsys, "transcribe", str(f), "--format", "md", "--timeout", "60")
    assert code == 0 and "texto 13s" in out


def test_failure_exit_code_and_json(lib, tmp_path, capsys):
    f = speech(tmp_path)
    with FakeWorker(lib, StubEngine(fail=RuntimeError("boom"))):
        code, out, err = run(capsys, "transcribe", str(f), "--wait", "--json", "--timeout", "60")
    assert code == 1
    (entry,) = json.loads(out)["recordings"]
    assert entry["input"] == str(f) and entry["result"] == "failed" and "boom" in entry["error"]
    assert set(entry["recording"]) == set(cli_json.KEYS)


def test_rejected_file(lib, tmp_path, capsys):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF-1.4 not audio")
    code, out, err = run(capsys, "transcribe", str(pdf), "--json")
    assert code == 1
    (entry,) = json.loads(out)["recordings"]
    assert entry["result"] == "rejected" and entry["recording"] is None and entry["error"]


def test_folder_to_output_folder(lib, tmp_path, capsys):
    d = tmp_path / "meetings"
    d.mkdir()
    speech(d, "lunes.wav")
    speechy_wav(d / "martes.wav", [(1, False), (4, True), (1, False)])  # different sound, not a duplicate
    notes = tmp_path / "notes"
    with FakeWorker(lib):
        code, out, err = run(capsys, "transcribe", str(d), "--format", "md", "--out", str(notes),
                             "--json", "--timeout", "60")
    assert code == 0, err
    res = json.loads(out)["recordings"]
    assert sorted(Path(e["output"]).name for e in res) == ["lunes.md", "martes.md"]
    assert (notes / "lunes.md").read_text().startswith("# lunes")


def test_progress_lines_when_captured(lib, tmp_path, capsys):
    # Pauses long enough to split passages, and a slow engine, so the poll sees it running.
    f = speechy_wav(tmp_path / "long.wav", [(1, False)] + [(20, True), (4, False)] * 6)
    with FakeWorker(lib, StubEngine(delay=0.8)):
        code, _, err = run(capsys, "transcribe", str(f), "--wait", "--timeout", "60")
    assert code == 0
    lines = [ln for ln in err.splitlines() if ln.startswith(lib.all()[0].id)]
    assert lines and len(lines) <= 20, err
    assert "\r" not in err
    assert any(" transcribing " in ln for ln in lines), err


def test_info_and_list_json(lib, tmp_path, capsys):
    f = speech(tmp_path)
    with FakeWorker(lib):
        run(capsys, "transcribe", str(f), "--wait", "--timeout", "60")
    rec = lib.all()[0]
    code, out, _ = run(capsys, "info", rec.id, "--json")
    d = json.loads(out)
    assert code == 0 and tuple(d) == cli_json.KEYS
    assert d["transcript_status"] == "done" and d["files"]["transcript"] == str(rec.path(TRANSCRIPT).resolve())
    code, out, _ = run(capsys, "list", "--json")
    listed = json.loads(out)
    assert listed["recordings"] == [d] and listed["sets"] == []
    code, out, _ = run(capsys, "info", rec.id)
    assert "Transcript: done" in out
    assert run(capsys, "info", "nope")[0] == 1


def test_running_progress_in_info(lib, tmp_path, capsys):
    f = speech(tmp_path)
    run(capsys, "transcribe", str(f))
    rec = lib.all()[0]
    rec.path("transcribe.progress.json").write_text(json.dumps(
        {"stage": "transcribing", "done": 3, "total": 12, "eta_s": 42.4}))
    d = json.loads(run(capsys, "info", rec.id, "--json")[1])
    assert d["transcript_status"] == "running"
    assert d["progress"] == {"stage": "transcribing", "fraction": 0.25, "eta_s": 42}


def test_preflight_before_importing(lib, tmp_path, capsys, monkeypatch):
    f = speech(tmp_path)
    monkeypatch.setattr(models, "all_cached", lambda: False)
    code, _, err = run(capsys, "transcribe", str(f))
    assert code == 1 and "echo-app models download" in err
    monkeypatch.setattr(features, "transcription_installed", lambda: False)
    code, _, err = run(capsys, "transcribe", str(f))
    assert code == 1 and "install.sh --with-transcription" in err
    assert lib.all() == []


def test_help_has_examples_and_exit_codes(capsys):
    with pytest.raises(SystemExit):
        cli.main(["transcribe", "--help"])
    out = capsys.readouterr().out
    assert "examples:" in out and "exit codes:" in out and "--timeout 540" in out


def test_headless_without_qt(tmp_path):
    f = speech(tmp_path)
    script = f"""
import sys
from echo_app import cli, features, models
features.transcription_installed = lambda: True
models.all_cached = lambda: True
codes = [cli.main(["transcribe", {str(f)!r}, "--format", "md", "--timeout", "0.2"]),
         cli.main(["list", "--json"]), cli.main(["info", "nope", "--json"])]
print("CODES", codes, "QT", any(m.startswith("PySide6") for m in sys.modules))
"""
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM")}
    env["PYTHONPATH"] = str(SRC)
    r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120)
    assert "CODES [3, 0, 1] QT False" in r.stdout, r.stderr
