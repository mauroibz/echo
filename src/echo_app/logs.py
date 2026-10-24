"""Rotating log files in the state directory."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import paths


def setup(name: str, verbose: bool = False) -> None:
    d = paths.state_dir()
    d.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(d / f"{name}.log", maxBytes=2_000_000,
                                                   backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(process)d %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    if verbose:
        err = logging.StreamHandler(sys.stderr)
        err.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(err)
