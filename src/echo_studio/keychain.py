"""The API key in the desktop's keyring (Secret Service: KDE Wallet, GNOME Keyring), through
`secret-tool`, so it is stored encrypted with the user's login and never sits in a file (stdlib only).

The key is passed on standard input and read from standard output, never on a command line, where
other users' `ps` could see it. One key per server (by host name), so a local server and a cloud
provider each keep their own.
"""

from __future__ import annotations

import os
import shutil
import subprocess

SERVICE = "echo-studio"
STORE_TIMEOUT_S = 120  # a locked wallet asks for its password: give the user time to type it
LOOKUP_TIMEOUT_S = 60


class KeychainError(Exception):
    """The keyring is missing or refused; the message says what to do."""


def _tool() -> str | None:
    if os.environ.get("ECHO_NO_KEYRING") == "1":
        return None  # tests: never the real wallet
    return shutil.which("secret-tool")


def available() -> bool:
    return _tool() is not None


def _attrs(server: str) -> list[str]:
    return ["service", SERVICE, "server", server or "-"]


def _run(args: list[str], timeout: float, stdin: str | None = None) -> subprocess.CompletedProcess:
    tool = _tool()
    if tool is None:
        raise KeychainError("no keyring found: install secret-tool (libsecret), or set the key "
                            "in the environment")
    try:
        return subprocess.run([tool, *args], input=stdin, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise KeychainError(f"the keyring did not answer: {e}") from None


def lookup(server: str) -> str:
    """The saved key, or "" when there is none or no keyring."""
    if not available():
        return ""
    try:
        r = _run(["lookup", *_attrs(server)], LOOKUP_TIMEOUT_S)
    except KeychainError:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def store(server: str, key: str) -> None:
    r = _run(["store", f"--label=Echo Studio API key ({server})", *_attrs(server)], STORE_TIMEOUT_S, key)
    if r.returncode != 0:
        raise KeychainError(f"the keyring refused the key: {r.stderr.strip() or 'no reason given'}")


def clear(server: str) -> None:
    if available():
        _run(["clear", *_attrs(server)], LOOKUP_TIMEOUT_S)
