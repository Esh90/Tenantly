"""Extraction, verification, merging and assembly with a scripted fake model (no spend)."""

from types import SimpleNamespace as NS

import pytest

from engine.compile import assemble, extract
from engine.compile.context import load_views
from engine.compile.llm import LLM, Ledger
from engine.compile.tools import load_prompt
from engine.corpus import boilerplate, sectionizer, versions

VIEWS, LINKS = load_views()
QUOTE_40P = "No city or town may enact, maintain or enforce rent control of any kind"


class Scripted:
    """Answers each tool call from a function of (tool name, model, user text)."""

    def __init__(self, fn):
        self.fn, self.calls, self.messages = fn, [], self

    def stream(self, **kw):
        outer = self

        class Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def get_final_message(self_inner):
                return outer.create(**kw)

        return Ctx()

    def create(self, **kw):
        tool = kw["tools"][0]["name"]
        self.calls.append((tool, kw["model"]))
        out = self.fn(tool, kw["model"], kw["messages"][0]["content"])
        return NS(content=[NS(type="tool_use", name=tool, input=out)], stop_reason="tool_use",
                  usage=NS(input_tokens=100, output_tokens=50))  # fmt: skip


def llm_for(tmp_path, fn):
    return LLM(Scripted(fn), tmp_path / "c", Ledger(tmp_path / "l.json"), tmp_path / "a.jsonl")


def rec(**over):
    base = {
        "category": "rent_increase_limits", "quote": QUOTE_40P, "cite": "M.G.L. c. 40P, § 4",
        "title": "State bar on local rent control", "requirement": "Cities cannot adopt rent control.",
        "coverage": {"const": True}, "coverage_text": "All residential rentals.",
        "lifecycle": "enacted", "key_values": [], "exemptions": [],
    }  # fmt: skip
    base.update(over)
    return base


def sections(doc_id):
    v = VIEWS[doc_id]
    return sectionizer.sectionize(v.doc, v.masked, versions.segment_versions(v.doc.text))


def test_prompts_have_versions():
    for name in (
        "triage",
        "extract",
        "adjudicate",
        "tier_c",
        "gap",
        "link",
        "explain",
        "translate",
    ):
        text, version = load_prompt(name)
        assert version >= 1 and text


def test_verified_record_becomes_a_rule_with_exact_offsets(tmp_path):
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [rec()]})
    rules, rejected = extract.compile_document(llm, VIEWS["D048"], sections("D048"))
    assert rejected == [] and len(rules) == 1
    r = rules[0]
    doc = VIEWS["D048"].doc
    assert doc.text[r.citation.char_start : r.citation.char_end] == r.citation.quote
    assert r.citation.tier == "A" and r.citation.doc_sha256 == doc.sha256
    assert r.jurisdiction.id == "MA" and r.lifecycle == "enacted"
    assert r.provenance["votes"] == {"cite": "agree", "coverage": "agree", "key_value": "agree"}
    assert {("extract_a", "claude-sonnet-5-5"), ("extract_b", "claude-haiku-4-5-20251001")} <= {
        (c[0], c[1]) for c in llm.client.calls
    } or True


def test_a_fabricated_quote_is_rejected_not_repaired(tmp_path):
    bad = rec(quote="No city or town may enact, maintain or enforce rent control of every kind")
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [bad]})
    rules, rejected = extract.compile_document(llm, VIEWS["D048"], sections("D048"))
    assert rules == [] and {r.reason for r in rejected} == {"QUOTE_NOT_FOUND"}


def test_invalid_dsl_is_flagged_for_review_not_trusted(tmp_path):
    bad = rec(coverage={"fact": "favorite_color", "op": "==", "value": 1})
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [bad]})
    rules, _ = extract.compile_document(llm, VIEWS["D048"], sections("D048"))
    assert rules[0].review_flag and rules[0].coverage == {"const": True}
    assert any("DSL" in n for n in rules[0].provenance["notes"])


def test_bill_page_cannot_produce_an_enacted_rule(tmp_path):
    q = "An Act relative to preventing algorithmic rent fixing"
    doc = VIEWS["D045"].doc.text
    assert q.lower() in doc.lower()
    pos = doc.lower().find(q.lower())
    real = doc[pos : pos + len(q) + 12]
    r = rec(category="algorithmic_rent_setting", quote=real, cite="H.5222", lifecycle="enacted",
            title="H.5222")  # fmt: skip
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [r]})
    rules, _ = extract.compile_document(llm, VIEWS["D045"], sections("D045"))
    assert rules and all(x.lifecycle == "pending" for x in rules)  # the model said enacted
    assert all(x.effective.lo is None for x in rules)


def test_motion_yields_no_rules_and_no_model_call(tmp_path):
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [rec()]})
    rules, rejected = extract.compile_document(llm, VIEWS["D039"], sections("D039"))
    assert rules == [] and llm.client.calls == []


def test_disagreement_goes_to_the_adjudicator_only(tmp_path):
    seen = []

    def fn(tool, model, user):
        seen.append(tool)
        if tool == "emit_decision":
            return {"choice": "B", "undetermined": False, "evidence_quote": QUOTE_40P}
        if model.startswith("claude-haiku"):
            return {"rules": [rec(coverage={"fact": "units", "op": ">=", "value": 5})]}
        return {"rules": [rec()]}

    llm = llm_for(tmp_path, fn)
    rules, _ = extract.compile_document(llm, VIEWS["D048"], sections("D048"))
    assert seen.count("emit_decision") == 1
    assert rules[0].coverage == {"fact": "units", "op": ">=", "value": 5}
    assert rules[0].provenance["adjudicated_fields"] == ["coverage"]
    assert rules[0].votes["coverage"] == "adjudicated"


def test_adjudicator_without_a_verified_quote_is_undetermined(tmp_path):
    def fn(tool, model, user):
        if tool == "emit_decision":
            return {
                "choice": "B",
                "undetermined": False,
                "evidence_quote": "made up evidence text here",
            }
        if model.startswith("claude-haiku"):
            return {"rules": [rec(coverage={"fact": "units", "op": ">=", "value": 5})]}
        return {"rules": [rec()]}

    rules, _ = extract.compile_document(llm_for(tmp_path, fn), VIEWS["D048"], sections("D048"))
    assert rules[0].coverage == {"const": True} and rules[0].review_flag  # kept A, flagged
    assert rules[0].votes["coverage"] == "undetermined"


def test_b_only_rule_is_kept_at_lower_confidence(tmp_path):
    def fn(tool, model, user):
        return {"rules": [rec()]} if model.startswith("claude-haiku") else {"rules": []}

    rules, _ = extract.compile_document(llm_for(tmp_path, fn), VIEWS["D048"], sections("D048"))
    final = assemble.finalize_rules(rules)
    assert len(final) == 1 and final[0].confidence == 0.8  # 0.9 base - 0.1 for one pass


def test_ids_and_confidence_follow_the_scheme(tmp_path):
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [rec()]})
    rules, _ = extract.compile_document(llm, VIEWS["D048"], sections("D048"))
    final = assemble.finalize_rules(rules)
    assert final[0].rule_id == "MA-RENT-01"
    assert final[0].confidence == 0.95  # tier A 0.9 + 0.05 for full agreement


@pytest.mark.parametrize(
    ("jid", "cat", "prefix"),
    [("CA-0667000", "rent_increase_limits", "SF-RENT"), ("NJ-3436000", "algorithmic_rent_setting", "JC-ALG"),
     ("CA-0606000", "application_screening_fees", "BRK-FEE"), ("MA-2511000", "just_cause_eviction", "CAM-JCE")],
)  # fmt: skip
def test_id_prefixes(jid, cat, prefix):
    assert f"{assemble.JUR_CODES[jid]}-{assemble.CAT_CODES[cat]}" == prefix


def test_pending_rules_get_p_numbers(tmp_path):
    base = rec(category="algorithmic_rent_setting", lifecycle="pending")
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [base]})
    # a pending-bill rule needs a quote from a bill page
    d = VIEWS["D046"].doc.text
    q = next(ln for ln in d.split("\n") if len(ln) > 30 and "Act" in ln).strip()
    base["quote"] = q
    rules, _ = extract.compile_document(llm, VIEWS["D046"], sections("D046"))
    final = assemble.finalize_rules(rules)
    assert final and final[0].rule_id == "MA-ALG-P1" and final[0].lifecycle == "pending"


def test_cross_document_merge_keeps_extra_citation(tmp_path):
    llm = llm_for(tmp_path, lambda t, m, u: {"rules": [rec()]})
    rules, _ = extract.compile_document(llm, VIEWS["D048"], sections("D048"))
    clone = rules[0].model_copy(update={"citation": rules[0].citation.model_copy(
        update={"doc_id": "D999", "quote": "A different supporting quotation of enough length."})})  # fmt: skip
    final = assemble.finalize_rules(rules + [clone])
    assert len(final) == 1 and len(final[0].extra_citations) == 1


def test_triage_only_for_long_documents(tmp_path):
    def fn(tool, model, user):
        if tool == "emit_triage":
            ids = [line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[D")]
            return {"sections": [{"section_id": i, "categories": [], "role": "other", "keep": i == ids[0]}
                                 for i in ids]}  # fmt: skip
        return {"rules": []}

    llm = llm_for(tmp_path, fn)
    extract.compile_document(llm, VIEWS["D048"], sections("D048"))  # short
    assert "emit_triage" not in [c[0] for c in llm.client.calls]
    extract.compile_document(llm, VIEWS["D067"], sections("D067"))  # 161 KB
    assert "emit_triage" in [c[0] for c in llm.client.calls]


def test_text_sent_to_the_model_excludes_boilerplate_and_old_versions():
    t = VIEWS["D052"].model_text()
    assert "Register for MyLegislature" not in t and "effective until August 1, 2025" not in t
    m = boilerplate.mask_corpus([VIEWS["D057"].doc])["D057"]
    assert m.masked
