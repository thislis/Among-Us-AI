from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable

import psutil


@lru_cache(maxsize=1)
def _normalized_candidates(process_name: str) -> tuple[str, ...]:
    """Return normalized executable name candidates for matching."""
    name = process_name.strip().lower()
    candidates = {name}
    if name.endswith(".exe"):
        candidates.add(name[:-4])
    return tuple(sorted(filter(None, candidates)))


def _iter_process_names() -> Iterable[str]:
    for proc in psutil.process_iter(["name", "exe"]):
        info = proc.info
        for key in ("name", "exe"):
            value = info.get(key)
            if not value:
                continue
            base = os.path.basename(str(value)).strip().lower()
            if base:
                yield base


def is_process_running(process_name: str = "Among Us.exe") -> bool:
    """Return True if a process with the given name is running."""
    candidates = set(_normalized_candidates(process_name))
    try:
        for pname in _iter_process_names():
            if pname in candidates:
                return True
    except Exception:
        return False
    return False

