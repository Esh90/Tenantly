"""Latency benchmark (PLAN.md 5.5): lookups against a running API, plus the same question
answered the common way (retrieve text, ask a model) as an honest baseline.

Run: ``uv run python -m eval.bench_latency --api http://localhost:8000``.
The baseline makes three real model calls (a few cents); pass --no-baseline to skip it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from datetime import UTC, datetime

from engine import config
from engine.io import atomic_write_json

SERVER_MS: list[float] = []


def _record(r) -> None:
    """The API reports its own time in Server-Timing: total;dur=<ms>."""
    for part in (r.headers.get("Server-Timing") or "").split(","):
        if part.strip().startswith("total"):
            SERVER_MS.append(float(part.split("dur=")[1]))


def get(url: str) -> float:
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310
        r.read()
        _record(r)
    return (time.perf_counter() - t) * 1000


def post(url: str, body: dict) -> float:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        r.read()
        _record(r)
    return (time.perf_counter() - t) * 1000


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def llm_baseline(address_label: str) -> float:
    """Retrieve the most relevant document text by keyword, then ask a model. Returns ms."""
    import anthropic

    docs = sorted((config.TEXT_DIR).glob("D*.txt"))
    words = [w.lower() for w in address_label.replace(",", " ").split() if len(w) > 3]
    scored = sorted(
        docs, key=lambda p: -sum(p.read_text(encoding="utf-8").lower().count(w) for w in words)
    )[:3]
    context = "\n\n".join(p.read_text(encoding="utf-8")[:12000] for p in scored)
    t = time.perf_counter()
    anthropic.Anthropic(timeout=150, max_retries=1).messages.create(
        model=config.MODEL_STRONG, max_tokens=600,
        messages=[{"role": "user", "content": f"Using only this text, which housing rules apply at {address_label} on 2026-10-01?\n\n{context}"}],
    )  # fmt: skip
    return (time.perf_counter() - t) * 1000


def main() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--no-baseline", action="store_true")
    a = ap.parse_args()
    base = a.api.rstrip("/") + "/v1"
    ids = [f"A{i:04d}" for i in range(1, 501)]
    get(base + "/health")  # wake a sleeping instance
    for aid in ids[:5]:
        get(f"{base}/lookup/{aid}")
    SERVER_MS.clear()
    lookups = [get(f"{base}/lookup/{ids[i * 5 % 500]}?as_of=2026-10-01") for i in range(a.n)]
    lookup_server = list(SERVER_MS)
    SERVER_MS.clear()
    timelines = [get(f"{base}/timeline/{ids[i * 7 % 500]}") for i in range(a.n)]
    custom = [
        post(
            f"{base}/lookup/custom",
            {"address_id": ids[i * 3 % 500], "as_of": "2026-10-01", "facts": {"year_built": 1985}},
        )
        for i in range(a.n)
    ]
    out = {
        "measured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "api": a.api, "samples": a.n,
        "lookup_p50_ms": round(statistics.median(lookup_server), 2), "lookup_p95_ms": round(pct(lookup_server, 95), 2),
        "lookup_client_p50_ms": round(statistics.median(lookups), 2), "lookup_client_p95_ms": round(pct(lookups, 95), 2),
        "timeline_p50_ms": round(statistics.median(timelines), 2), "timeline_p95_ms": round(pct(timelines, 95), 2),
        "custom_p50_ms": round(statistics.median(custom), 2), "custom_p95_ms": round(pct(custom, 95), 2),
        "llm_baseline_ms": None,
    }  # fmt: skip
    if not a.no_baseline:
        runs = [llm_baseline("3515 Fillmore St, San Francisco, CA") for _ in range(2)]
        out["llm_baseline_ms"] = round(statistics.median(runs), 0)
    atomic_write_json(config.ARTIFACTS / "eval" / "latency.json", out)
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()
