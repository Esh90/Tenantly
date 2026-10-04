"""Eval isolation: nothing under engine/ may touch the silver key or the eval/ directory.

``artifacts/eval/`` (measured reports written by the pipeline) is a different place and is fine.
"""

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine"
SEP = "[/\\\\]"  # a forward or back slash inside a regex
FORBIDDEN = [
    re.compile(r"silver_key"),
    # a string literal that starts with the repo-root eval/ directory
    re.compile("[\"']eval" + SEP),
    # Path joins from the repo root or a package parent into eval
    re.compile(r"(ROOT|parent|parents\[\d\])\s*/\s*[\"']eval[\"']"),
    re.compile(r"^\s*(from|import)\s+eval\b", re.M),
]
INGEST_PATHS = {"cli.py", "ingest.py"}


def _offenders(text: str) -> list[str]:
    return [p.pattern for p in FORBIDDEN if p.search(text)]


def test_no_eval_leakage_into_engine():
    offenders = []
    for path in ENGINE.rglob("*.py"):
        for pat in _offenders(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(ENGINE)}: {pat}")
    assert offenders == []


def test_forbidden_patterns_actually_match():
    assert _offenders("open('eval/silver_key.yaml')")
    assert _offenders('Path("eval/selfscore.py")')
    assert _offenders("ROOT / 'eval' / 'x'")
    assert _offenders('Path(__file__).parent / "eval"')
    assert _offenders("from eval import selfscore")
    assert _offenders("import eval.selfscore")


def test_artifacts_eval_reports_are_allowed():
    assert not _offenders('config.ARTIFACTS / "eval" / "facts_report.json"')
    assert not _offenders('"artifacts/eval/selfscore.json"')
    assert not _offenders("def evaluate(x): return retrieval")


def test_hour16_only_read_on_ingest_paths():
    offenders = []
    for path in ENGINE.rglob("*.py"):
        if path.name in INGEST_PATHS or "ingest" in path.parts:
            continue
        if "hour16" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ENGINE)))
    assert offenders == []
