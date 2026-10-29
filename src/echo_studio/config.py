"""Studio's settings: the language-model server, in a file of its own next to Echo's (stdlib only).

Echo's settings.toml has no Studio keys, so removing Studio leaves Echo's file as it was. The API
key is kept apart from both, readable only by the user: settings files get copied between
machines and pasted into bug reports.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from echo_app import paths
from echo_app.fsutil import atomic_write_text, fsync_dir

log = logging.getLogger(__name__)

KEY_ENV = "ECHO_LLM_API_KEY"


@dataclass
class Config:
    llm_url: str = ""  # an OpenAI-compatible base URL, ending in /v1
    llm_model: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.llm_url.strip() and self.llm_model.strip())


def config_path() -> Path:
    return paths.config_dir() / "studio.toml"


def key_path() -> Path:
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
    return c


def save(c: Config) -> None:
    def q(v: str) -> str:
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

    atomic_write_text(config_path(), "# Echo Studio settings\n\n"
                      "# OpenAI-compatible server, ending in /v1. Empty = summaries off\n"
                      f"llm_url = {q(c.llm_url)}\n\n# Model name on that server\nllm_model = {q(c.llm_model)}\n",
                      mkdir=True)


def enabled() -> bool:
    return load().enabled


def api_key() -> str:
    if os.environ.get(KEY_ENV):
        return os.environ[KEY_ENV].strip()
    try:
        return key_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_key(key: str) -> None:
    """Write (or with an empty key, remove) the key file, readable by the user only."""
    p = key_path()
    if not key.strip():
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    # As fsutil's atomic write, but the temporary file stays 0600 (mkstemp's mode): the key is never
    # readable by others, not even for the moment before the rename.
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key.strip() + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    fsync_dir(p.parent)


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
