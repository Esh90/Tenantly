"""Atomic, deterministic artifact writes: temp file then rename, sorted keys, no ASCII escaping."""

from __future__ import annotations

import json
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def atomic_write_jsonl(path: Path, rows) -> None:
    lines = (json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows)
    atomic_write_text(path, "\n".join(lines) + "\n")
