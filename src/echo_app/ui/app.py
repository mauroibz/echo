"""Application bootstrap: single instance, first run, main window."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME, settings
from ..library import Library

log = logging.getLogger(__name__)


def server_name() -> str:
    import getpass

    # Per user: the uid on POSIX, the account name on Windows (named pipes are machine-wide).
    return f"echo-app-{os.getuid() if hasattr(os, 'getuid') else getpass.getuser()}"


def forward_to_running(files: list[str]) -> bool:
    """If Echo is already running, hand it our files and ask it to show itself."""
    sock = QLocalSocket()
    sock.connectToServer(server_name())
    if not sock.waitForConnected(300):
        return False
    sock.write(json.dumps({"show": True, "files": files}).encode() + b"\n")
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class InstanceServer(QLocalServer):
    def __init__(self, on_message, parent=None):
        super().__init__(parent)
        self.on_message = on_message
        self.newConnection.connect(self._accept)
        QLocalServer.removeServer(server_name())  # stale socket from a crash
        self.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.listen(server_name()):
            log.warning("single-instance server failed: %s", self.errorString())

    def _accept(self):
        while self.hasPendingConnections():
            sock = self.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(sock.deleteLater)

    def _read(self, sock):
        data = bytes(sock.readAll()).decode(errors="replace")
        for line in data.splitlines():
            try:
                self.on_message(json.loads(line))
            except json.JSONDecodeError:
                pass


def run(argv: list[str]) -> int:
    files = [str(Path(a).resolve()) for a in argv[1:] if not a.startswith("-") and Path(a).exists()]
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("echo-app")
    QApplication.setDesktopFileName("echo-app")
    app = QApplication(argv[:1])
    if forward_to_running(files):
        return 0
    first_run = not settings.settings_path().exists()
    cfg, warning = settings.load()
    if first_run:
        settings.save(cfg)
    from . import theme
    from .common import UiState, app_icon
    from .main_window import MainWindow

    theme.apply(cfg.theme, app)
    hints = app.styleHints()
    hints.colorSchemeChanged.connect(lambda _s: theme.apply(theme.mode(), app) if theme.mode() == theme.SYSTEM else None)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    lib = Library(cfg.data_path)
    from .. import extensions

    window_class = next((c for c in extensions.call("window_class") if c is not None), MainWindow)
    try:
        win = window_class(lib, UiState())
    except Exception:
        if window_class is MainWindow:
            raise
        log.exception("extension window failed; opening Echo's own")
        win = MainWindow(lib, UiState())
    extensions.call("attach_window", win)

    def on_message(msg: dict):
        if msg.get("show"):
            win.show_window()
        if msg.get("files"):
            win.import_paths([Path(f) for f in msg["files"]])

    server = InstanceServer(on_message)
    win.show()
    if warning:
        QTimer.singleShot(300, lambda: QMessageBox.warning(win, APP_NAME, warning))
    if first_run:
        QTimer.singleShot(200, win.show_welcome)
    if files:
        QTimer.singleShot(400, lambda: win.import_paths([Path(f) for f in files]))
    code = app.exec()
    server.close()
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run(sys.argv))
