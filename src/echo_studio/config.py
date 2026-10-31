"""Studio's settings: the language-model server, in a file of its own next to Echo's (stdlib only).

Echo's settings.toml has no Studio keys, so removing Studio leaves Echo's file as it was. The API
key is in neither: it is in the desktop's keyring (`keychain`), or in the environment. Settings
files get copied between machines and pasted into bug reports.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from echo_app import paths
from echo_app.fsutil import atomic_write_text

from . import keychain

log = logging.getLogger(__name__)

KEY_ENV = "ECHO_LLM_API_KEY"


@dataclass
class Config:
    llm_url: str = ""  # an OpenAI-compatible base URL ending in /v1, or https://api.anthropic.com/v1
    llm_model: str = ""
    auto_summarize: bool = True  # summarize each transcript as soon as it is ready (the user's choice)
    auto_title: bool = True  # a short title from the summary for recordings whose title is automatic
    auto_record: bool = True  # record the calendar's meetings with a video link when they start

    @property
    def enabled(self) -> bool:
        return bool(self.llm_url.strip() and self.llm_model.strip())


def config_path() -> Path:
    return paths.config_dir() / "studio.toml"


def old_key_path() -> Path:
    """Where Studio kept the key before the keyring; moved into the keyring when found."""
    return paths.config_dir() / "llm.key"


def load() -> Config:
    c = Config()
    try:
        raw = tomllib.loads(config_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return c
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
        log.warning("Studio settings unreadable (%s); summaries are off until they are saved again", e)
        return c
    for name in ("llm_url", "llm_model"):
        if isinstance(raw.get(name), str):
            setattr(c, name, raw[name].strip())
    for name in ("auto_summarize", "auto_title", "auto_record"):
        if isinstance(raw.get(name), bool):
            setattr(c, name, raw[name])
    return c


def save(c: Config) -> None:
    def q(v: str) -> str:
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

    atomic_write_text(config_path(), "# Echo Studio settings\n\n"
                      "# OpenAI-compatible server, ending in /v1. Empty = summaries off\n"
                      f"llm_url = {q(c.llm_url)}\n\n# Model name on that server\nllm_model = {q(c.llm_model)}\n\n"
                      "# Summarize each transcript as soon as it is ready\n"
                      f"auto_summarize = {'true' if c.auto_summarize else 'false'}\n\n"
                      "# A short title from the summary, for recordings you did not name\n"
                      f"auto_title = {'true' if c.auto_title else 'false'}\n\n"
                      "# Record the calendar's meetings that have a video link, when they start\n"
                      f"auto_record = {'true' if c.auto_record else 'false'}\n",
                      mkdir=True)


def enabled() -> bool:
    return load().enabled


_keys: dict[str, str] = {}  # per server, read from the keyring once: a locked wallet asks only once


def api_key(url: str | None = None) -> str:
    """The key for `url` (the configured server by default): the environment's, else the keyring's."""
    if os.environ.get(KEY_ENV):
        return os.environ[KEY_ENV].strip()
    server = host(load().llm_url if url is None else url)
    if server not in _keys:
        _keys[server] = keychain.lookup(server) or _move_old_key(server)
    return _keys[server]


def _move_old_key(server: str) -> str:
    """A key left in llm.key by an earlier Studio goes into the keyring, and the file away."""
    p = old_key_path()
    try:
        key = p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    try:
        keychain.store(server, key)
    except keychain.KeychainError as e:
        log.warning("Studio's key is still in %s: %s", p, e)
        return key
    p.unlink(missing_ok=True)
    return key


def save_key(key: str, url: str | None = None) -> None:
    """Keep (or with an empty key, forget) the key for `url` in the keyring.
    Raises keychain.KeychainError when there is no keyring to keep it in."""
    server = host(load().llm_url if url is None else url)
    key = key.strip()
    if not os.environ.get(KEY_ENV) and key == api_key(url):
        return  # unchanged: do not wake the wallet
    if key:
        keychain.store(server, key)
    else:
        keychain.clear(server)
    _keys[server] = key


def host(url: str) -> str:
    return urlsplit(url.strip()).hostname or ""


def is_local(url: str) -> bool:
    """On this computer or its private network: transcripts sent there stay with the user."""
    h = host(url)
    if not h:
        return True
    if h == "localhost" or h.endswith(".local") or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local
