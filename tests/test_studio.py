"""Echo Studio's summaries against a fake OpenAI-compatible server (no network, no model)."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QCheckBox, QToolButton

from echo_app import cli, export, extensions
from echo_app.library import Library
from echo_studio import actions, config, keychain, llm, summary, templates
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures
from test_vault import SEGS, _rec


class FakeServer:
    """Answers /v1/chat/completions with a canned summary and /v1/models with one model."""

    def __init__(self):
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.reply = "# Tema\n- Lucía habló del precio.\n\n# Próximos pasos\n- **Enviar la propuesta** (Lucía)\n---"
        self.status = 200
        self.models = ["modelo-a"]
        self.paths: list[str] = []
        self.all_requests: list[dict] = []
        self.mail = "Asunto: Seguimiento de la charla\n\nHola a todos:\n\n- Lucía envía la propuesta."
        self.actions = json.dumps([{"text": "Enviar la propuesta", "owner": "lucia", "due": "2026-10-31",
                                    "at": "0:06"}])
        self.stop_reason = "end_turn"
        self.title = '"Precio nuevo con Lucía."'
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                server.headers.append(dict(self.headers))
                server.paths.append(self.path)
                self._send(200, {"data": [{"id": m} for m in server.models]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                first = (body.get("system") or body["messages"][0]["content"])
                server.all_requests.append(body)
                helpers = ("Write a title", "You extract the action items", "You write the follow-up",
                           "You answer questions", "You turn a question")
                if not first.startswith(helpers):
                    server.requests.append(body)  # the summaries; titles and action items apart
                server.headers.append(dict(self.headers))
                server.paths.append(self.path)
                if server.status != 200:
                    self._send(server.status, {"error": {"message": "invalid api key"}})
                    return
                if self.path.endswith("/messages"):  # Anthropic's Messages API
                    self._send(200, {"content": [{"type": "thinking", "thinking": ""},
                                                 {"type": "text", "text": server.reply}],
                                     "stop_reason": server.stop_reason})
                    return
                canned = {"Write a title": server.title, "You extract the action items": server.actions,
                          "You write the follow-up email": server.mail,
                          "You answer questions about one meeting": "Se habló del precio [0:06].",
                          "You turn a question": '["precio", "@nadie precio"]',
                          "You answer questions about past meetings": "Lucía habló del precio [1]."}
                reply = next((v for k, v in canned.items() if first.startswith(k)), server.reply)
                self._send(200, {"choices": [{"message": {"content": reply}}]})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server(monkeypatch):
    s = FakeServer()
    config.save(config.Config(s.url, "modelo-a"))
    monkeypatch.delenv(config.KEY_ENV, raising=False)
    yield s
    s.close()


FAKE_SECRET_TOOL = """\
import json, sys
from pathlib import Path
store = Path(sys.argv[0]).with_name("secrets.json")
data = json.loads(store.read_text()) if store.exists() else {}
cmd, args = sys.argv[1], [a for a in sys.argv[2:] if not a.startswith("--")]
key = " ".join(args)
if cmd == "store":
    data[key] = sys.stdin.read()
elif cmd == "lookup":
    if key not in data:
        sys.exit(1)
    sys.stdout.write(data[key])
elif cmd == "clear":
    data.pop(key, None)
store.write_text(json.dumps(data))
"""


@pytest.fixture(autouse=True)
def keyring(tmp_path, monkeypatch):
    """A fake `secret-tool` on PATH, keeping secrets in a file next to it: the real one would be the
    user's wallet. Returns the file, to check what was stored and that no key went elsewhere."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "secret-tool"
    tool.write_text(f"#!{sys.executable}\n" + FAKE_SECRET_TOOL)
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("ECHO_NO_KEYRING", raising=False)
    monkeypatch.setattr(config, "_keys", {})
    return bin_dir / "secrets.json"


@pytest.fixture
def studio(monkeypatch):
    """Echo with Studio loaded, as `bin/echo-app` runs it from a checkout that has it."""
    monkeypatch.delenv("ECHO_NO_EXTENSIONS", raising=False)
    extensions.loaded.cache_clear()
    yield
    extensions.loaded.cache_clear()


def test_off_until_a_server_and_model_are_set():
    assert not config.enabled()
    config.save(config.Config("http://127.0.0.1:8080/v1", ""))
    assert not config.enabled()
    config.save(config.Config("http://127.0.0.1:8080/v1", "m"))
    assert config.enabled() and config.load().llm_model == "m"


def test_key_in_the_keyring_never_in_a_file(tmp_path, keyring):
    from echo_app import settings, paths

    url = "https://api.example.com/v1"
    config.save(config.Config(url, "m"))
    config.save_key("sk-secreta", url)
    assert config.api_key() == "sk-secreta" and "sk-secreta" in keyring.read_text()
    config._keys.clear()
    assert config.api_key() == "sk-secreta"  # read back from the keyring
    assert config.api_key("http://127.0.0.1:8080/v1") == ""  # one key per server
    settings.save(settings.load()[0])
    for f in paths.config_dir().rglob("*"):
        assert not f.is_file() or "sk-secreta" not in f.read_text(), f
    config.save_key("", url)
    config._keys.clear()
    assert config.api_key() == ""


def test_old_key_file_moves_into_the_keyring(keyring):
    config.save(config.Config("https://api.example.com/v1", "m"))
    config.old_key_path().write_text("sk-vieja\n")
    assert config.api_key() == "sk-vieja"
    assert not config.old_key_path().exists() and "sk-vieja" in keyring.read_text()


def test_no_keyring_says_so(monkeypatch):
    monkeypatch.setenv("ECHO_NO_KEYRING", "1")
    assert config.api_key("https://api.example.com/v1") == ""
    with pytest.raises(keychain.KeychainError, match="no keyring"):
        config.save_key("sk-x", "https://api.example.com/v1")


def test_anthropic_spoken_natively(tmp_path, server, monkeypatch):
    monkeypatch.setattr(llm, "ANTHROPIC_HOSTS", {"127.0.0.1"})
    config.save(config.Config(server.url, "modelo-a"))
    config.save_key("sk-ant-test", server.url)
    assert llm.models() == ["modelo-a"] and server.paths[-1] == "/v1/models?limit=1000"
    text = llm.complete("Sistema", "Transcripción")
    assert text == server.reply.strip() and server.paths[-1] == "/v1/messages"
    req, headers = server.requests[-1], {k.lower(): v for k, v in server.headers[-1].items()}
    assert req["system"] == "Sistema" and req["messages"] == [{"role": "user", "content": "Transcripción"}]
    assert "temperature" not in req and req["max_tokens"] == llm.ANTHROPIC_MAX_TOKENS
    assert req["fallbacks"] == "default" and headers["anthropic-beta"] == llm.ANTHROPIC_FALLBACK_BETA
    assert headers["x-api-key"] == "sk-ant-test" and headers["anthropic-version"] == llm.ANTHROPIC_VERSION
    assert "authorization" not in headers
    server.stop_reason = "refusal"
    with pytest.raises(llm.LLMError, match="declined"):
        llm.complete("Sistema", "Transcripción")
    server.stop_reason = "max_tokens"
    with pytest.raises(llm.LLMError, match="cut off"):
        llm.complete("Sistema", "Transcripción")


def test_local_or_remote():
    for url in ("http://127.0.0.1:8080/v1", "http://localhost:11434/v1", "http://192.168.1.20:8000/v1",
                "http://gpu-box.local:8080/v1", "http://[::1]:8080/v1"):
        assert config.is_local(url), url
    for url in ("https://api.openai.com/v1", "https://openrouter.ai/api/v1", "http://8.8.8.8/v1"):
        assert not config.is_local(url), url


def test_summary_request_and_file(tmp_path, server, monkeypatch):
    monkeypatch.setenv(config.KEY_ENV, "sk-test")
    rec = _rec(Library(tmp_path / "data"))
    rec.update(context_line="Entrevista sobre precios")
    data = summary.write(rec)
    assert len(server.requests) == 1
    req = server.requests[0]
    assert req["model"] == "modelo-a" and req["max_tokens"] == llm.MAX_TOKENS
    system, user = req["messages"][0]["content"], req["messages"][1]["content"]
    assert "Próximos pasos" in system and "Write in Spanish." in system
    assert "Title: Charla con Lucía" in user and "About: Entrevista sobre precios" in user
    assert "Hablemos del precio." in user
    assert server.headers[0]["Authorization"] == "Bearer sk-test"
    saved = json.loads(rec.path(summary.FILE).read_text())
    assert saved == data and saved["text"].endswith("(Lucía)")  # the trailing --- is dropped
    assert saved["server"] == "127.0.0.1" and not summary.stale(rec)
    rec.path("transcript.edited.txt").write_text("Otro texto.\n")
    assert summary.stale(rec)


def test_no_key_no_authorization_header(tmp_path, server):
    summary.write(_rec(Library(tmp_path / "data")))
    assert "Authorization" not in server.headers[0]


def test_server_error_keeps_the_earlier_summary(tmp_path, server):
    rec = _rec(Library(tmp_path / "data"))
    summary.write(rec)
    before = rec.path(summary.FILE).read_text()
    server.status = 401
    with pytest.raises(llm.LLMError, match="401: invalid api key"):
        summary.write(rec)
    assert rec.path(summary.FILE).read_text() == before


def test_unreachable_server(tmp_path):
    config.save(config.Config("http://127.0.0.1:9/v1", "m"))
    with pytest.raises(llm.LLMError, match="could not reach 127.0.0.1"):
        summary.write(_rec(Library(tmp_path / "data")))


def test_thinking_is_removed(tmp_path, server):
    server.reply = "<think>\nlet me see\n</think>\n# Tema\n- punto"
    assert summary.write(_rec(Library(tmp_path / "data")))["text"] == "# Tema\n- punto"


def test_retry_without_max_tokens(tmp_path, server, monkeypatch):
    calls = []
    real = llm._request

    def fake(url, payload, timeout, key=None):
        calls.append(dict(payload or {}))
        if payload and "max_tokens" in payload:
            raise llm.LLMError("the server answered 400: Unsupported parameter: 'max_tokens'")
        return real(url, payload, timeout, key)

    monkeypatch.setattr(llm, "_request", fake)
    summary.write(_rec(Library(tmp_path / "data")))
    assert "max_tokens" in calls[0] and "max_tokens" not in calls[1]


def test_notes_and_markers_lead_the_summary(tmp_path, server):
    rec = _rec(Library(tmp_path / "data"))
    assert summary.guide(rec) == "" and summary.source_sha(rec) == summary.sha(summary.source_text(rec))
    summary.write(rec)
    assert "Notes:" not in server.requests[-1]["messages"][-1]["content"]
    assert summary.GUIDE.strip() not in server.requests[-1]["messages"][0]["content"]
    rec.update(notes="Ver si aceptan el precio nuevo.")
    rec.set_markers([{"at": 6.5, "note": "precio"}, {"at": 66.0, "note": ""}])
    assert summary.stale(rec)  # a note or a marker changes what the summary is made from
    g = summary.guide(rec)
    assert g.startswith("Notes:\nVer si aceptan el precio nuevo.") and "- at 0:06: precio" in g
    assert "- at 1:06: (no note)" in g and "Said around it:" in g
    summary.write(rec)
    req = server.requests[-1]
    assert summary.GUIDE.strip() in req["messages"][0]["content"] and g in req["messages"][-1]["content"]
    assert not summary.stale(rec)


def test_templates_by_tag(tmp_path, server):
    rec = _rec(Library(tmp_path / "data"))
    summary.write(rec)
    assert templates.GENERAL in server.requests[-1]["messages"][0]["content"]
    rec.set_tags(["cliente-x", "template:Entrevista"])
    assert templates.of(rec) == "Entrevista" and summary.stale(rec)  # the template is part of the source
    data = summary.write(rec)
    system = server.requests[-1]["messages"][0]["content"]
    assert templates.BUILT_IN["entrevista"] in system and templates.GENERAL not in system
    assert data["template"] == "Entrevista" and not summary.stale(rec)
    # The user's own template wins over a built-in with the same name; names list both.
    templates.user_dir().mkdir(parents=True)
    (templates.user_dir() / "entrevista.md").write_text("- Una sección por candidato.\n")
    (templates.user_dir() / "directorio.md").write_text("- Una sección por tema del directorio.\n")
    assert "directorio" in templates.names() and "uno-a-uno" in templates.names()
    assert summary.stale(rec)
    summary.write(rec)
    assert "Una sección por candidato." in server.requests[-1]["messages"][0]["content"]
    templates.set_for(rec, None)
    assert rec.meta.tags == ["cliente-x"] and templates.resolve(rec)[0] is None
    templates.set_for(rec, "nada")  # unknown: the general prompt
    assert templates.resolve(rec) == (None, templates.GENERAL)


def test_cli_template(tmp_path, server, capsys, studio):
    from echo_app import settings

    s = settings.load()[0]
    s.data_dir = str(tmp_path / "data")
    settings.save(s)
    rec = _rec(Library(tmp_path / "data"))
    assert cli.main(["summarize", rec.id, "--template", "nada"]) == 2
    assert cli.main(["summarize", rec.id, "--template", "clase"]) == 0
    assert templates.BUILT_IN["clase"] in server.requests[-1]["messages"][0]["content"]
    assert Library(tmp_path / "data").get(rec.id).meta.tags == ["template:clase"]


def test_title_from_the_summary_only_when_automatic(window, lib, server, studio):
    rec = _rec(lib)
    rec.update(title="Bueno, empezamos", title_auto=True)
    window.model.refresh()
    _attach(window)
    window.transcribed.emit(rec.id)
    assert wait_until(lambda: lib.get(rec.id).meta.title == "Precio nuevo con Lucía")
    assert lib.get(rec.id).meta.title_auto  # still Echo's: a new transcript may replace it
    other = _rec(lib, title="Mi título")
    window.transcribed.emit(other.id)
    assert wait_until(lambda: other.path(summary.FILE).exists())
    pump(200)
    assert lib.get(other.id).meta.title == "Mi título"
    titles = [r for r in server.all_requests if r["messages"][0]["content"].startswith("Write a title")]
    assert len(titles) == 1


def _model_item(text, owner="", due="", at=None):
    return {"text": text, "owner": owner, "due": due, "at": at, "context": "", "discarded": False, "edited": False,
            "origin": "model", "key": actions.fold_tag(text)}


def test_action_items_parsed_tolerantly():
    reply = 'Acá van:\n```json\n[{"text": " Enviar  la propuesta ", "owner": "Lucía", "due": "2026-11-02",' \
            ' "at": "1:02:03"}, {"text": "", "owner": "x"}, {"text": "Llamar", "due": "el viernes", "at": "x"}]\n```'
    items = actions.parse(reply)
    assert items == [_model_item("Enviar la propuesta", "Lucía", "2026-11-02", 3723.0), _model_item("Llamar")]
    assert actions.parse("no hay") == [] and actions.parse("[{bad json") == []


def test_action_items_keep_the_users_work(tmp_path, server):
    lib = Library(tmp_path / "data")
    rec = _rec(lib)
    data = summary.write(rec)
    summary.finish(rec, data)
    req = server.all_requests[-1]
    assert req["messages"][0]["content"].startswith("You extract the action items")
    assert "Transcript with times:" in req["messages"][1]["content"] and "[0:06]" in req["messages"][1]["content"]
    assert actions.load(rec)["items"] == [_model_item("Enviar la propuesta", "lucia", "2026-10-31", 6.0)]
    actions.update(rec, 0, text="Enviar la propuesta de precios", context="la versión con descuento")
    actions.add(rec, "Reservar sala", owner="Ana")
    server.actions = json.dumps([{"text": "enviar la PROPUESTA", "owner": "Lucía"}, {"text": "Llamar a Ana"},
                                 {"text": "Mandar la grabación"}])
    summary.finish(rec, data)
    actions.discard(rec, 2, True)
    server.actions = json.dumps([{"text": "Enviar la propuesta", "at": "0:09"}, {"text": "Mandar la grabación"}])
    summary.finish(rec, data)
    items = actions.load(rec)["items"]
    assert [(i["text"], i["discarded"], i["origin"]) for i in items] == [
        ("Enviar la propuesta de precios", False, "model"),  # the user's text, its first time
        ("Mandar la grabación", True, "model"),  # still discarded
        ("Reservar sala", False, "user")]  # added by hand: kept; "Llamar a Ana" is gone with the model
    assert items[0]["edited"] and items[0]["context"] == "la versión con descuento" and items[0]["at"] == 6.0
    assert "done" not in items[0]
    assert [i["text"] for i in actions.assigned_to(lib, "ANA")] == ["Reservar sala"]
    assert actions.assigned_to(lib, "nadie") == []


def test_version_1_actions_are_read(tmp_path):
    lib = Library(tmp_path / "data")
    rec = _rec(lib)
    rec.path(actions.FILE).write_text(json.dumps({"version": 1, "items": [
        {"text": "Llamar a Ana", "owner": "Lucía", "due": "", "at": 3.0, "done": True}]}))
    assert actions.load(rec)["items"] == [_model_item("Llamar a Ana", "Lucía", "", 3.0)]


def test_polishing_items_in_the_summary_view(window, lib, server, studio):
    from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QPushButton

    from echo_studio.ui import SummaryView

    rec = _rec(lib)
    window.model.refresh()
    _attach(window)
    assert not any(type(w).__name__ == "PendingScreen" for w in window._screen_buttons)
    view = window.views.views()[0]
    assert isinstance(view, SummaryView)
    window._select(rec.id)
    window.transcribed.emit(rec.id)
    assert wait_until(lambda: actions.load(lib.get(rec.id)) is not None)
    view.show_subject(lib.get(rec.id), None)
    assert view.actions_box.isVisibleTo(view) and not view.actions.findChildren(QCheckBox)
    texts = lambda: [lbl.text() for lbl in view.actions.findChildren(QLabel)]  # noqa: E731
    assert "Enviar la propuesta" in texts()
    assert any(t.startswith("lucia") and "by " in t for t in texts())
    played = []
    window._seek_and_play = played.append
    next(b for b in view.actions.findChildren(QToolButton) if b.objectName() == "pill").click()
    assert played == [6.0]
    edit = next(b for b in view.actions.findChildren(QToolButton) if b.toolTip() == "Edit")
    edit.click()
    view.actions.findChildren(QLineEdit)[0].setText("Enviar la propuesta final")
    view.actions.findChildren(QPlainTextEdit)[0].setPlainText("pedirle el número a Tomás")
    next(b for b in view.actions.findChildren(QPushButton) if b.text() == "Save").click()
    it = actions.load(lib.get(rec.id))["items"][0]
    assert it["text"] == "Enviar la propuesta final" and it["edited"] and it["context"] == "pedirle el número a Tomás"
    assert "pedirle el número a Tomás" in texts()
    next(b for b in view.actions.findChildren(QToolButton) if b.toolTip() == "Discard").click()
    assert actions.load(lib.get(rec.id))["items"][0]["discarded"] and "1 discarded" in texts()
    next(b for b in view.actions.findChildren(QPushButton) if b.text() == "Show").click()
    next(b for b in view.actions.findChildren(QToolButton) if b.toolTip() == "Restore").click()
    assert not actions.load(lib.get(rec.id))["items"][0]["discarded"]
    view.add_btn.click()
    view.actions.findChildren(QLineEdit)[0].setText("Reservar sala")
    next(b for b in view.actions.findChildren(QPushButton) if b.text() == "Save").click()
    assert [i["origin"] for i in actions.load(lib.get(rec.id))["items"]] == ["model", "user"]
    import echo_studio

    [(title, section)] = echo_studio.person_sections("Lucia")  # People: the items assigned to them
    assert title == "Action items" and not section.findChildren(QCheckBox)
    assert "Enviar la propuesta final" in [lbl.text() for lbl in section.findChildren(QLabel)]


def test_follow_up_draft(window, lib, server, studio, capsys, tmp_path, monkeypatch):
    from echo_app import settings
    from echo_studio import followup
    from echo_studio.ui import FollowUpDialog, SummaryView

    rec = _rec(lib)
    summary.finish(rec, summary.write(rec))
    subject, body = followup.draft(rec)
    assert subject == "Seguimiento de la charla" and body.startswith("Hola a todos:")
    req = server.all_requests[-1]["messages"][1]["content"]
    assert "Action items:\n- Enviar la propuesta (lucia), by 2026-10-31" in req
    assert followup.mailto("A b", "c&d") == "mailto:?subject=A%20b&body=c%26d"
    window.model.refresh()
    _attach(window)
    view = window.views.views()[0]
    assert isinstance(view, SummaryView)
    window._select(rec.id)
    window.views.buttons[1].click()
    assert view.follow_btn.isVisible()
    view.follow_up()
    assert wait_until(lambda: any(isinstance(w, FollowUpDialog) for w in view.findChildren(FollowUpDialog)))
    dlg = view.findChildren(FollowUpDialog)[0]
    assert dlg.subject.text() == "Seguimiento de la charla"
    opened = []
    monkeypatch.setattr("echo_studio.ui.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    dlg.open_mail()
    assert opened and opened[0].startswith("mailto:?subject=Seguimiento")
    s = settings.load()[0]
    s.data_dir = str(lib.data_dir)
    settings.save(s)
    assert cli.main(["summarize", rec.id, "--follow-up"]) == 0
    assert "Subject: Seguimiento de la charla" in capsys.readouterr().out


def test_ask_a_recording_and_the_library(window, lib, server, studio, capsys, monkeypatch):
    from echo_app import settings
    from echo_studio import ask
    from echo_studio.ask_ui import AskScreen, AskView

    rec = _rec(lib)
    said = ask.ask_recording(rec, "¿De qué hablaron?", [("¿Quién estaba?", "Lucía [0:00].")])
    user = server.all_requests[-1]["messages"][1]["content"]
    assert "[0:06] Hablemos del precio." in user and "Q: ¿Quién estaba?" in user and user.endswith("¿De qué hablaron?")
    assert ask.link_times(said, rec.id) == f"Se habló del precio [0:06](echo:{rec.id}@6)."
    assert ask.parse_link(f"echo:{rec.id}@6") == (rec.id, 6.0) and ask.parse_link("https://x") is None
    assert ask.link_refs("Sí [1, 3] y [2].", [{"id": "a", "start": 1.5}, {"id": "b", "start": 0.0}]) == \
        "Sí [[1](echo:a@1.5), 3] y [[2](echo:b@0)]."
    window.model.refresh()
    _attach(window)
    view = next(v for v in window.views.views() if isinstance(v, AskView))
    window._select(rec.id)
    assert view.chat.isVisibleTo(view)
    played = []
    monkeypatch.setattr(window, "_seek_and_play", played.append)
    view.chat.box.setText("¿De qué hablaron?")
    view.chat.ask()
    assert wait_until(lambda: len(view.chat.turns) == 1)
    assert "echo:" in view.chat.turns[0][2]
    view.chat._open(QUrl(f"echo:{rec.id}@6"))
    assert played == [6.0]
    screen = next(w for w in window._screen_buttons if isinstance(w, AskScreen))
    screen.chat.box.setText("¿Qué se dijo del precio?")
    screen.chat.ask()
    assert wait_until(lambda: len(screen.chat.turns) == 1)
    passages = server.all_requests[-1]["messages"][1]["content"]
    assert passages.startswith("Passages:\n\n[1] Charla con Lucía") and "Hablemos del precio." in passages
    assert f"(echo:{rec.id}@" in screen.chat.turns[0][2]
    s = settings.load()[0]
    s.data_dir = str(lib.data_dir)
    settings.save(s)
    assert cli.main(["ask", rec.id, "¿Precio?"]) == 0
    assert "Se habló del precio [0:06]." in capsys.readouterr().out
    assert cli.main(["ask", "¿Precio?"]) == 0
    out = capsys.readouterr().out
    assert "Lucía habló del precio [1]." in out and f"[1] Charla con Lucía ({rec.id}) at 0:" in out


def test_due_dates_read_as_days():
    from datetime import date, timedelta

    from echo_studio.actions_ui import fmt_due

    today = date.today()
    assert fmt_due(today.isoformat()) == f"by {today:%a %b %-d}"
    assert fmt_due((today - timedelta(days=3)).isoformat()).startswith("by ")  # never "late"
    assert fmt_due("bad") == "by bad"


def test_split_at_paragraphs():
    paras = [("palabra " * 1200).strip() + "." for _ in range(20)]  # ~9,600 characters each
    parts = summary.split("\n\n".join(paras))
    assert all(len(p) <= summary.PART_MAX for p in parts) and len(parts) == 5
    assert "\n\n".join(parts) == "\n\n".join(paras)
    long = ("Una frase larga. " * 4000).strip()
    cut = summary.split(long)
    assert all(len(p) <= summary.PART_MAX for p in cut) and all(p.endswith(".") for p in cut[:-1])


def test_long_transcript_in_parts_then_merged(tmp_path, server):
    rec = _rec(Library(tmp_path / "data"))
    text = "\n\n".join(("Se habló del tema número %d. " % i) * 300 for i in range(15))  # ~130,000 chars
    rec.path("transcript.edited.txt").write_text(text)
    seen = []
    summary.write(rec, progress=lambda d, t: seen.append((d, t)))
    parts = server.requests[:-1]
    assert len(parts) == len(summary.split(summary.source_text(rec))) >= 3
    assert all(len(p["messages"][1]["content"]) < summary.PART_MAX + 500 for p in parts)
    assert "part 1 of" in parts[0]["messages"][0]["content"]
    assert "Merge them into one summary" in server.requests[-1]["messages"][0]["content"]
    assert seen[-1] == (len(parts), len(parts) + 1)


def test_cli(tmp_path, server, capsys, studio):
    from echo_app import settings

    s = settings.load()[0]
    s.data_dir = str(tmp_path / "data")
    settings.save(s)
    rec = _rec(Library(tmp_path / "data"))
    assert cli.main(["summarize", rec.id, "--print"]) == 0
    assert "Lucía habló del precio." in capsys.readouterr().out
    assert cli.main(["summarize", rec.id, "--json"]) == 0  # current: no second request
    out = json.loads(capsys.readouterr().out)
    assert len(server.requests) == 1 and out[0]["id"] == rec.id and out[0]["summary"]["stale"] is False
    assert cli.main(["summarize", "nope"]) == 1
    config.save(config.Config("", ""))
    assert cli.main(["summarize", rec.id]) == 3
    assert "Summaries need a language-model server" in capsys.readouterr().err


def test_cli_data_out(tmp_path, server, capsys, studio):
    from echo_app import settings

    s = settings.load()[0]
    s.data_dir = str(tmp_path / "data")
    settings.save(s)
    lib = Library(tmp_path / "data")
    rec = _rec(lib)
    bare = _rec(lib)
    summary.finish(rec, summary.write(rec))
    actions.update(rec, 0, context="con el descuento")
    actions.add(rec, "Reservar sala", owner="Ana")
    capsys.readouterr()
    assert cli.main(["meetings", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in out] == [rec.id] and out[0]["action_items"] == 2
    assert out[0]["minutes"]["excerpt"] == "Lucía habló del precio. Enviar la propuesta (Lucía)"
    assert cli.main(["meetings", "--all"]) == 0 and bare.id in capsys.readouterr().out
    assert cli.main(["meetings", "--since", "mañana"]) == 2
    assert cli.main(["minutes", rec.id, "--json"]) == 0
    m = json.loads(capsys.readouterr().out)
    first = m["action_items"][0]
    assert m["minutes"]["text"].startswith("# Tema") and first["context"] == "con el descuento"
    assert first["at_stamp"] == "0:06" and "Lucía" in first["quote"] and first["recording"] == rec.id
    assert m["action_items"][1]["added_by_user"] is True
    assert cli.main(["minutes", rec.id]) == 0
    text = capsys.readouterr().out
    assert "## Action items" in text and "- Enviar la propuesta (lucia, by 2026-10-31, 0:06)\n  con el descuento" in text
    assert cli.main(["minutes", bare.id]) == 1
    actions.discard(rec, 1, True)
    assert cli.main(["actions", "--owner", "ana", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert cli.main(["actions", "--discarded", "--json"]) == 0
    assert [i["text"] for i in json.loads(capsys.readouterr().out)] == ["Enviar la propuesta", "Reservar sala"]
    assert cli.main(["actions", "--since", "today"]) == 0  # the test recordings were made today


def test_cli_all_summarizes_what_is_missing(tmp_path, server, capsys, studio):
    from echo_app import settings

    s = settings.load()[0]
    s.data_dir = str(tmp_path / "data")
    settings.save(s)
    lib = Library(tmp_path / "data")
    rec = _rec(lib)
    assert cli.main(["summarize"]) == 2
    assert cli.main(["summarize", "--all"]) == 0 and len(server.requests) == 1
    assert rec.path(summary.FILE).exists()
    assert cli.main(["summarize", "--all"]) == 0 and len(server.requests) == 1  # nothing left
    assert "0 recording(s)" in capsys.readouterr().err


def test_note_has_the_summary(tmp_path, server, studio):
    rec = _rec(Library(tmp_path / "data"))
    assert "## Resumen" not in export.to_markdown(rec)
    summary.write(rec)
    note = export.to_markdown(rec)
    assert "## Resumen\n\n### Tema\n- Lucía habló del precio." in note
    assert note.index("## Resumen") < note.index("Hola, soy Lucía.")


def test_doctor(server, studio):
    from echo_app import doctor

    checks = {c.name: c for c in extensions.gather("doctor_checks")}
    assert checks["Summaries server (127.0.0.1)"].status == doctor.OK
    server.models = ["otro"]
    assert extensions.gather("doctor_checks")[0].status == doctor.WARN
    config.save(config.Config("", ""))
    assert extensions.gather("doctor_checks") == []


def _attach(window):
    import echo_studio

    echo_studio.attach_window(window)


def test_window_unchanged_until_set_up(window, studio):
    _attach(window)
    assert window.views.views() == [] and not window.views.bar.isVisible()


def test_summary_view(window, lib, server, studio):
    from echo_studio.ui import SummaryView

    rec = _rec(lib)
    window.model.refresh()
    _attach(window)
    view = window.views.views()[0]
    assert isinstance(view, SummaryView) and window.views.bar.isVisible()
    window._select(rec.id)
    window.views.buttons[1].click()
    assert view.summarize_btn.isVisible() and view.summarize_btn.text() == "Summarize"
    view.summarize_btn.click()
    assert wait_until(lambda: rec.path(summary.FILE).exists() and "Lucía habló" in view.text.toPlainText())
    assert view.summarize_btn.text() == "Summarize again" and view.copy_btn.isVisible()
    view._fill_templates()
    names = [a.text() for a in view.template_menu.actions() if a.isCheckable()]
    assert names[0] == "General meeting" and "entrevista" in names
    view.use_template("entrevista")
    assert wait_until(lambda: (summary.load(lib.get(rec.id)) or {}).get("template") == "entrevista")
    assert "entrevista" in view.status.text()
    view.copy()
    from PySide6.QtWidgets import QApplication

    assert QApplication.clipboard().text().startswith("# Tema")
    rec.path("transcript.edited.txt").write_text("Otro texto.\n")
    view.show_subject(lib.get(rec.id), None)
    assert "changed since" in view.status.text()


def test_a_ready_transcript_is_summarized_on_its_own(window, lib, server, studio):
    from echo_studio.ui import SummaryView

    rec = _rec(lib)
    window.model.refresh()
    _attach(window)
    view = window.views.views()[0]
    assert isinstance(view, SummaryView)
    window._select(rec.id)
    window.transcribed.emit(rec.id)
    assert wait_until(lambda: rec.path(summary.FILE).exists())
    assert len(server.requests) == 1
    window.transcribed.emit(rec.id)  # current already: not again
    pump(200)
    assert len(server.requests) == 1
    # A failure is shown, and not tried again on its own until the transcript changes.
    rec.path("transcript.edited.txt").write_text("Otro texto.\n")
    server.status = 500
    window.transcribed.emit(rec.id)
    assert wait_until(lambda: "Summary failed" in view.status.text())
    window.transcribed.emit(rec.id)
    pump(200)
    assert len(server.requests) == 2
    # Turned off in Settings: nothing is sent.
    server.status = 200
    rec.path("transcript.edited.txt").write_text("Texto nuevo.\n")
    cfg = config.load()
    cfg.auto_summarize = False
    config.save(cfg)
    window.transcribed.emit(rec.id)
    pump(200)
    assert len(server.requests) == 2
    view.summarize_btn.click()  # pressing Summarize always tries
    assert wait_until(lambda: len(server.requests) == 3 and not summary.stale(lib.get(rec.id)))


def test_settings_page_turns_summaries_on(window, lib, qapp, studio):
    from echo_studio.ui import SettingsPage, SummaryView

    _attach(window)
    import echo_studio

    page = echo_studio.settings_pages()[0][1]
    assert isinstance(page, SettingsPage)
    page.url.setText("https://api.example.com/v1")
    assert page.warning.text() == "Each transcript is sent to api.example.com as soon as it is ready."
    page.auto.setChecked(False)
    assert page.warning.text() == "Transcripts you summarize are sent to api.example.com."
    page.auto.setChecked(True)
    with pytest.raises(ValueError, match="name the model"):
        page.apply()
    page.model.setText("modelo-a")
    page.key.setText("sk-nueva")
    page.apply()
    assert config.enabled() and config.api_key() == "sk-nueva"
    assert any(isinstance(v, SummaryView) for v in window.views.views())  # no restart needed
    page.url.setText("http://127.0.0.1:8080/v1")
    assert not page.warning.text()
