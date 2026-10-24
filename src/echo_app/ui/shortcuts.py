"""System-wide shortcuts through the XDG desktop portal (KDE Plasma 6, GNOME 46 and newer).

The portal shows its own dialog the first time, where the user confirms or changes the keys, and
remembers them. The session lives as long as the connection that created it, so a thread keeps
one connection open while the window runs and turns the portal's Activated signals into Qt
signals. Where there is no portal, Settings explains how to bind `echo-app record --toggle` and
`--quick-note` to keys in the desktop's own settings.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

SHORTCUTS = {
    "record-toggle": ("Start or stop recording", "CTRL+ALT+R"),
    "quick-note": ("Record a quick note; again to stop and copy its text", "CTRL+ALT+N"),
}
PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
INTERFACE = "org.freedesktop.portal.GlobalShortcuts"


def _connect():
    from jeepney.io.blocking import open_dbus_connection

    return open_dbus_connection(bus="SESSION")


def available() -> bool:
    """The session has a desktop portal with GlobalShortcuts."""
    if os.name == "nt":
        return False
    try:
        from jeepney import DBusAddress, Properties

        conn = _connect()
        try:
            addr = DBusAddress(PORTAL[1], bus_name=PORTAL[0], interface=INTERFACE)
            reply = conn.send_and_get_reply(Properties(addr).get("version"), timeout=3)
            return reply.header.message_type.name == "method_return"
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 - no bus, no portal, no jeepney: no global shortcuts
        log.info("no global shortcuts portal: %s", e)
        return False


class GlobalShortcuts(QObject):
    activated = Signal(str)  # shortcut id, delivered on the GUI thread
    status = Signal(str)  # "bound", "declined" or "unavailable", with details in the log

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="global-shortcuts", daemon=True)
        self._thread.start()

    def _request(self, conn, method: str, signature: str, args: tuple, options: dict):
        """A portal call: methods answer with a Request object whose Response signal has the result."""
        from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
        from jeepney.io.blocking import Proxy

        token = "echo" + secrets.token_hex(6)
        sender = conn.unique_name[1:].replace(".", "_")
        path = f"{PORTAL[1]}/request/{sender}/{token}"
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=path)
        Proxy(message_bus, conn).AddMatch(rule)
        addr = DBusAddress(PORTAL[1], bus_name=PORTAL[0], interface=INTERFACE)
        with conn.filter(rule) as queue:
            conn.send_and_get_reply(new_method_call(addr, method, signature,
                                                    (*args, {"handle_token": ("s", token), **options})))
            # BindShortcuts waits for the user in the portal's dialog.
            code, results = conn.recv_until_filtered(queue, timeout=None if method == "BindShortcuts" else 20).body
        return code, results

    def _run(self):
        try:
            from jeepney import MatchRule, message_bus
            from jeepney.io.blocking import Proxy

            conn = self._conn = _connect()
            code, res = self._request(conn, "CreateSession", "a{sv}", (),
                                      {"session_handle_token": ("s", "echo" + secrets.token_hex(6))})
            if code != 0:
                raise RuntimeError(f"CreateSession answered {code}")
            session = res["session_handle"][1]
            shortcuts = [(sid, {"description": ("s", desc), "preferred_trigger": ("s", trigger)})
                         for sid, (desc, trigger) in SHORTCUTS.items()]
            rule = MatchRule(type="signal", interface=INTERFACE, member="Activated", path=None)
            Proxy(message_bus, conn).AddMatch(rule)
            with conn.filter(rule) as queue:
                code, res = self._request(conn, "BindShortcuts", "oa(sa{sv})sa{sv}", (session, shortcuts, ""), {})
                if code != 0:
                    log.info("global shortcuts declined (%d)", code)
                    self.status.emit("declined")
                    return
                bound = {sid: props.get("trigger_description", ("s", ""))[1] for sid, props in res["shortcuts"][1]}
                log.info("global shortcuts bound: %s", bound)
                self.status.emit("bound")
                while not self._stop.is_set():
                    try:
                        msg = conn.recv_until_filtered(queue, timeout=1.0)
                    except TimeoutError:
                        continue
                    sess, sid, _ts, _opts = msg.body
                    if sess == session and sid in SHORTCUTS:
                        self.activated.emit(sid)
        except Exception as e:  # noqa: BLE001 - any failure leaves the manual route, which Settings explains
            if not self._stop.is_set():
                log.info("global shortcuts unavailable: %s", e)
                self.status.emit("unavailable")
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def stop(self):
        self._stop.set()
