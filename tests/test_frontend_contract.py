"""The frontend's TypeScript types and the API models must describe the same fields."""

import re
from pathlib import Path

import pytest

import engine.models as m

TYPES = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "api" / "types.ts"


def _top_fields(body: str) -> set[str]:
    depth, cur, parts = 0, "", []
    for ch in body:
        if ch in "{[<(":
            depth += 1
        if ch in "}]>)":
            depth -= 1
        if ch in ";\n" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return {mm.group(1) for f in parts if (mm := re.match(r"\s*(\w+)\??\s*:", f))}


def _interfaces() -> dict[str, set[str]]:
    ts = TYPES.read_text(encoding="utf-8")
    out = {}
    for mt in re.finditer(r"export interface (\w+)\s*\{", ts):
        i, depth = mt.end(), 1
        while depth:
            depth += (ts[i] == "{") - (ts[i] == "}")
            i += 1
        out[mt.group(1)] = _top_fields(ts[mt.end() : i - 1])
    return out


@pytest.mark.skipif(not TYPES.exists(), reason="frontend not present")
def test_every_ts_interface_matches_its_model_fields():
    ifaces = _interfaces()
    assert len(ifaces) >= 25
    for name, ts_fields in ifaces.items():
        cls = getattr(m, name, None)
        assert cls is not None, f"no API model for {name}"
        py_fields = {(v.alias or k) for k, v in cls.model_fields.items()}
        assert ts_fields == py_fields, (name, sorted(ts_fields ^ py_fields))
