"""Eval isolation: nothing under engine/ may touch the silver key or eval fixtures."""

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine"
SEP = "[/\\\\]"  # a forward or back slash inside a regex character class
FORBIDDEN = [
    re.compile(r"silver_key"),
    re.compile("(^|[\"'/\\\\])eval" + SEP),
    re.compile(r"^\s*(from|import)\s+eval\b", re.M),
]
INGEST_PATHS = {"cli.py", "ingest.py"}


def test_no_eval_leakage_into_engine():
    offenders = []
    for path in ENGINE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pat in FORBIDDEN:
            if pat.search(text):
                offenders.append(f"{path.relative_to(ENGINE)}: {pat.pattern}")
    assert offenders == []


def test_forbidden_patterns_actually_match():
    assert FORBIDDEN[0].search("open('eval/silver_key.yaml')")
    assert FORBIDDEN[1].search('Path("eval/selfscore.py")')
    assert FORBIDDEN[1].search("ROOT / 'eval\\\\x'")
    assert FORBIDDEN[2].search("from eval import selfscore")
    assert not any(p.search("def evaluate(x): return retrieval") for p in FORBIDDEN)


def test_hour16_only_read_on_ingest_paths():
    offenders = []
    for path in ENGINE.rglob("*.py"):
        if path.name in INGEST_PATHS or "ingest" in path.parts:
            continue
        if "hour16" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ENGINE)))
    assert offenders == []
