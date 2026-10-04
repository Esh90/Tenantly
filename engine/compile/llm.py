"""The only place that calls a model (PLAN.md 11.2): content-addressed cache, spend ledger,
audit log and a hard budget cap. Nothing on the lookup path imports this module.

Notes on the current API (verified against the Claude API reference):
- ``claude-sonnet-5-5`` and ``claude-opus-5-5`` reject forced ``tool_choice``. Every call uses
  ``tool_choice: auto`` plus an instruction that names the tool, and is retried if the model
  does not call it. ``claude-haiku-4-5`` follows the same path for uniformity.
- Sonnet 5.5 and Opus 5.5 always think; depth is controlled with ``output_config.effort``.
- Cache reads cost 0.1x and cache writes 1.25x the input price.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine import config
from engine.io import atomic_write_json

log = logging.getLogger("tenantly.llm")

# USD per million tokens (input, output). Source: Claude API model table.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
}
CACHE_READ = 0.1
CACHE_WRITE = 1.25
EFFORT_MODELS = ("claude-sonnet-5", "claude-opus-5")  # prefixes that accept output_config.effort

CACHE_DIR = config.ARTIFACTS / "compile"
LEDGER_PATH = config.ARTIFACTS / "ledger.json"
AUDIT_PATH = config.ARTIFACTS / "audit" / "compile_audit.jsonl"


class BudgetExceeded(RuntimeError):
    pass


class NoToolCall(RuntimeError):
    pass


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def cost_usd(model: str, usage: dict) -> float:
    pin, pout = PRICES[model]
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    return (inp * pin + cw * pin * CACHE_WRITE + cr * pin * CACHE_READ + out * pout) / 1_000_000


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: legal text averages about 4 characters per token."""
    return max(1, len(text) // 3)


@dataclass
class Result:
    output: dict
    cache_hit: bool
    cost: float
    key: str


class Ledger:
    """Running spend, by stage and model. Persisted after every paid call."""

    def __init__(self, path: Path = LEDGER_PATH, cap: float = config.BUDGET_USD_CAP):
        self.path = path
        self.cap = min(cap, 18.0)  # never above the project cap
        self._lock = threading.Lock()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.total: float = data.get("total_usd", 0.0)
        self.by_stage: dict[str, float] = data.get("by_stage", {})
        self.by_model: dict[str, float] = data.get("by_model", {})
        self.calls: int = data.get("paid_calls", 0)
        self.cache_hits: int = data.get("cache_hits", 0)
        self.tokens: dict[str, int] = data.get("tokens", {"input": 0, "output": 0})

    def check(self, estimate: float) -> None:
        if self.total + estimate > self.cap:
            raise BudgetExceeded(
                f"spend {self.total:.2f} + estimate {estimate:.2f} would pass cap {self.cap:.2f}"
            )

    def add(self, stage: str, model: str, cost: float, usage: dict) -> None:
        with self._lock:
            self.total += cost
            self.by_stage[stage] = self.by_stage.get(stage, 0.0) + cost
            self.by_model[model] = self.by_model.get(model, 0.0) + cost
            self.calls += 1
            self.tokens["input"] += usage.get("input_tokens", 0)
            self.tokens["output"] += usage.get("output_tokens", 0)
            self._save()

    def hit(self) -> None:
        with self._lock:
            self.cache_hits += 1
            self._save()

    def _save(self) -> None:
        atomic_write_json(
            self.path,
            {
                "total_usd": round(self.total, 6),
                "cap_usd": self.cap,
                "by_stage": {k: round(v, 6) for k, v in sorted(self.by_stage.items())},
                "by_model": {k: round(v, 6) for k, v in sorted(self.by_model.items())},
                "paid_calls": self.calls,
                "cache_hits": self.cache_hits,
                "tokens": self.tokens,
                "prices_per_mtok": {m: list(p) for m, p in sorted(PRICES.items())},
            },
        )


class LLM:
    def __init__(
        self,
        client: Any | None = None,
        cache_dir: Path = CACHE_DIR,
        ledger: Ledger | None = None,
        audit_path: Path = AUDIT_PATH,
        concurrency: int = 4,
    ):
        self._client = client
        self.cache_dir = cache_dir
        self.ledger = ledger or Ledger()
        self.audit_path = audit_path
        self._sem = threading.Semaphore(concurrency)
        self._audit_lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(max_retries=5)  # SDK backs off on 429/5xx
        return self._client

    # ---- cache ----
    def key(self, stage: str, stage_version: int, model: str, prompt_version: int, system: str,
            user: str, tool: dict, effort: str | None) -> str:  # fmt: skip
        return sha(
            canonical([stage, stage_version, model, prompt_version, system, user, tool, effort])
        )

    def _path(self, stage: str, key: str) -> Path:
        return self.cache_dir / stage / f"{key}.json"

    def cached(self, stage: str, key: str) -> dict | None:
        p = self._path(stage, key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _audit(self, row: dict) -> None:
        with self._audit_lock:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")

    # ---- the call ----
    def call(
        self,
        *,
        stage: str,
        model: str,
        system: str,
        user: str,
        tool: dict,
        prompt_version: int,
        stage_version: int = 1,
        effort: str | None = "low",
        max_tokens: int = 16000,
        ref: str | None = None,
    ) -> Result:
        """Run one forced-output call. ``tool`` is {name, description, input_schema}."""
        key = self.key(stage, stage_version, model, prompt_version, system, user, tool, effort)
        hit = self.cached(stage, key)
        base = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "stage": stage, "model": model,
            "prompt_version": prompt_version, "input_sha": sha(system + "\n" + user), "ref": ref,
            "key": key,
        }  # fmt: skip
        if hit is not None:
            self.ledger.hit()
            self._audit({**base, "cache_hit": True, "output_sha": sha(canonical(hit["output"])),
                         "cost_usd": 0.0, "verifier": None})  # fmt: skip
            return Result(hit["output"], True, 0.0, key)

        pin, pout = PRICES[model]
        est = (estimate_tokens(system + user) * pin + 4000 * pout) / 1_000_000
        self.ledger.check(est)

        instruction = (
            f"\n\nRespond only by calling the tool `{tool['name']}` exactly once. "
            "Do not write any other text."
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": [tool],
            "tool_choice": {"type": "auto"},
            "messages": [{"role": "user", "content": user + instruction}],
        }
        if effort and model.startswith(EFFORT_MODELS):
            kwargs["output_config"] = {"effort": effort}

        usage_total: dict = {}
        tool_input: dict | None = None
        with self._sem:
            for attempt in range(1, 4):
                t0 = time.monotonic()
                resp = self.client.messages.create(**kwargs)
                usage = _usage_dict(resp)
                for k, v in usage.items():
                    usage_total[k] = usage_total.get(k, 0) + (v or 0)
                self.ledger.add(stage, model, cost_usd(model, usage), usage)
                log.info("llm stage=%s model=%s attempt=%d ms=%.0f stop=%s", stage, model, attempt,
                         (time.monotonic() - t0) * 1000, getattr(resp, "stop_reason", None))  # fmt: skip
                if getattr(resp, "stop_reason", None) == "max_tokens":
                    raise NoToolCall(f"{stage}: output hit max_tokens ({max_tokens})")
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                        tool_input = dict(block.input)
                        break
                if tool_input is not None:
                    break
                log.warning("llm stage=%s no tool call, retry %d", stage, attempt)
        if tool_input is None:
            raise NoToolCall(f"{stage}: model did not call {tool['name']}")
        total_cost = cost_usd(model, usage_total)
        p = self._path(stage, key)
        atomic_write_json(p, {"output": tool_input, "usage": usage_total, "cost_usd": total_cost,
                              "model": model, "prompt_version": prompt_version})  # fmt: skip
        self._audit({**base, "cache_hit": False, "output_sha": sha(canonical(tool_input)),
                     "cost_usd": round(total_cost, 6), "verifier": None})  # fmt: skip
        return Result(tool_input, False, total_cost, key)


def _usage_dict(resp: Any) -> dict:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
