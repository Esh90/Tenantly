"""The model wrapper: cache, ledger, audit, budget cap and retry. A fake client stands in for the
API, so these tests never spend money."""

import json
from types import SimpleNamespace as NS

import pytest

from engine.compile.llm import LLM, BudgetExceeded, Ledger, NoToolCall, cost_usd

TOOL = {"name": "emit_x", "description": "d", "input_schema": {"type": "object"}}


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def ok(payload, inp=1000, out=500, stop="tool_use"):
    return NS(
        content=[NS(type="tool_use", name="emit_x", input=payload)],
        stop_reason=stop,
        usage=NS(input_tokens=inp, output_tokens=out, cache_creation_input_tokens=0,
                 cache_read_input_tokens=0),
    )  # fmt: skip


def no_tool():
    return NS(content=[NS(type="text", text="hi")], stop_reason="end_turn",
              usage=NS(input_tokens=10, output_tokens=5))  # fmt: skip


def make(tmp_path, responses, cap=18.0):
    ledger = Ledger(tmp_path / "ledger.json", cap=cap)
    llm = LLM(FakeClient(responses), tmp_path / "compile", ledger, tmp_path / "audit.jsonl")
    return llm


def call(llm, user="u", model="claude-sonnet-5-5", **kw):
    return llm.call(stage="extract", model=model, system="s", user=user, tool=TOOL,
                    prompt_version=1, **kw)  # fmt: skip


def test_cost_formula_matches_published_prices():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert cost_usd("claude-sonnet-5-5", u) == pytest.approx(12.0)
    assert cost_usd("claude-opus-5-5", u) == pytest.approx(24.0)
    assert cost_usd("claude-haiku-4-5-20251001", u) == pytest.approx(6.0)
    cached = {"input_tokens": 0, "cache_read_input_tokens": 1_000_000,
              "cache_creation_input_tokens": 1_000_000}  # fmt: skip
    assert cost_usd("claude-sonnet-5-5", cached) == pytest.approx(0.2 + 2.5)


def test_second_identical_call_is_a_free_cache_hit(tmp_path):
    llm = make(tmp_path, [ok({"a": 1})])
    r1 = call(llm)
    r2 = call(llm)
    assert r1.output == r2.output == {"a": 1}
    assert (r1.cache_hit, r2.cache_hit) == (False, True)
    assert r2.cost == 0.0 and len(llm.client.calls) == 1
    assert llm.ledger.calls == 1 and llm.ledger.cache_hits == 1
    rows = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [r["cache_hit"] for r in rows] == [False, True]  # cache hits are still audited
    assert rows[0]["output_sha"] == rows[1]["output_sha"] and rows[1]["cost_usd"] == 0.0


def test_changed_input_or_prompt_version_misses_the_cache(tmp_path):
    llm = make(tmp_path, [ok({"a": 1}), ok({"a": 2}), ok({"a": 3})])
    call(llm, user="one")
    assert call(llm, user="two").cache_hit is False
    r = llm.call(stage="extract", model="claude-sonnet-5-5", system="s", user="one", tool=TOOL,
                 prompt_version=2)  # fmt: skip
    assert r.cache_hit is False and r.output == {"a": 3}


def test_ledger_persists_and_sums(tmp_path):
    llm = make(tmp_path, [ok({"a": 1}, inp=1_000_000, out=0)])
    call(llm)
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert data["total_usd"] == pytest.approx(2.0)
    assert data["by_stage"] == {"extract": pytest.approx(2.0)}
    assert Ledger(tmp_path / "ledger.json").total == pytest.approx(2.0)  # reloads


def test_budget_cap_raises_before_spending(tmp_path):
    llm = make(tmp_path, [ok({"a": 1})], cap=0.0001)
    with pytest.raises(BudgetExceeded):
        call(llm, user="x" * 3000)
    assert llm.client.calls == []


def test_cap_never_exceeds_project_limit(tmp_path):
    assert Ledger(tmp_path / "l.json", cap=100).cap == 18.0


def test_forced_tool_choice_is_never_sent(tmp_path):
    llm = make(tmp_path, [ok({"a": 1})])
    call(llm)
    sent = llm.client.calls[0]
    assert sent["tool_choice"] == {"type": "auto"}  # forced choice is a 400 on Sonnet/Opus 5.5
    assert "emit_x" in sent["messages"][0]["content"]
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in sent and sent["output_config"] == {"effort": "low"}


def test_effort_is_not_sent_to_haiku(tmp_path):
    llm = make(tmp_path, [ok({"a": 1})])
    call(llm, model="claude-haiku-4-5-20251001")
    assert "output_config" not in llm.client.calls[0]


def test_retries_when_the_model_skips_the_tool(tmp_path):
    llm = make(tmp_path, [no_tool(), ok({"a": 1})])
    assert call(llm).output == {"a": 1}
    assert len(llm.client.calls) == 2


def test_gives_up_after_three_attempts(tmp_path):
    llm = make(tmp_path, [no_tool(), no_tool(), no_tool()])
    with pytest.raises(NoToolCall):
        call(llm)
    assert llm.ledger.calls == 3  # every attempt was paid for and recorded


def test_truncated_output_is_an_error_not_a_partial_result(tmp_path):
    llm = make(tmp_path, [ok({"a": 1}, stop="max_tokens")])
    with pytest.raises(NoToolCall):
        call(llm)


def test_free_backup_model_takes_over_when_the_budget_is_spent(tmp_path, monkeypatch):
    from engine.compile import groq_fallback

    monkeypatch.setattr(groq_fallback, "available", lambda: True)
    monkeypatch.setattr(groq_fallback, "call_tool", lambda *a, **k: {"a": "from-backup"})
    llm = make(tmp_path, [ok({"a": 1})], cap=0.0001)
    r = call(llm, user="x" * 3000)
    assert r.output == {"a": "from-backup"} and r.cost == 0.0
    assert llm.client.calls == []  # nothing was sent to the paid API
    rows = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert rows[-1]["model"].startswith("groq:") and rows[-1]["fallback_for"] == "claude-sonnet-5-5"
    again = call(llm, user="x" * 3000)  # the backup answer is cached too
    assert again.cache_hit is True


def test_backup_is_not_used_when_unconfigured(tmp_path, monkeypatch):
    from engine.compile import groq_fallback

    monkeypatch.setattr(groq_fallback, "available", lambda: False)
    llm = make(tmp_path, [ok({"a": 1})], cap=0.0001)
    with pytest.raises(BudgetExceeded):
        call(llm, user="x" * 3000)
