"""Atomic, deterministic artifact writes: temp file then rename, sorted keys, no ASCII escaping."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # a unique temp name per process and thread, so concurrent writers never collide
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    for attempt in range(8):  # Windows can hold a file briefly (antivirus, indexers)
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    tmp.replace(path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def atomic_write_jsonl(path: Path, rows) -> None:
    lines = (json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows)
    atomic_write_text(path, "\n".join(lines) + "\n")
