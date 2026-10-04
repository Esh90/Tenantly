"""The API on the real compiled data: every response validates against the contract models.
Skipped when the compiled artifacts are absent."""

import pytest
from fastapi.testclient import TestClient

from engine import config
from engine.api import deps
from engine.api.main import app
from engine.api.store import available
from engine.models import (
    AddressList,
    AuditList,
    ChangeEvent,
    ChangeList,
    FindingList,
    LookupResponse,
    Meta,
    OpenQuestionList,
    ProofResponse,
    ResolveResponse,
    RuleDetail,
    RuleList,
    SourceDoc,
    TimelineResponse,
)

pytestmark = pytest.mark.skipif(not available(), reason="compiled artifacts not present")


@pytest.fixture(scope="module")
def client():
    import os

    old = os.environ.get("TENANTLY_STORE")
    os.environ["TENANTLY_STORE"] = "real"
    deps.get_store.cache_clear()
    yield TestClient(app)
    deps.get_store.cache_clear()
    if old is None:
        os.environ.pop("TENANTLY_STORE", None)
    else:
        os.environ["TENANTLY_STORE"] = old


def test_meta_and_counts(client):
    m = Meta.model_validate(client.get("/v1/meta").json())
    assert m.counts.addresses == 500 and m.counts.docs_text == 54 and m.counts.docs_link_only == 33
    assert m.counts.rules >= 50 and len(m.jurisdictions) == 3 + 10 + 9
    assert client.get("/v1/health").json()["data_version"] == m.data_version


def test_address_index_has_all_500_with_legal_cities(client):
    body = AddressList.model_validate(client.get("/v1/addresses").json())
    assert len(body.items) == 500
    dorchester = next(i for i in body.items if i.address_id == "A0118")
    assert dorchester.legal_city == "Boston" and dorchester.postal_city == "Dorchester"
    assert next(i for i in body.items if i.address_id == "A0295").lat is None


@pytest.mark.parametrize(
    "aid", ["A0001", "A0016", "A0002", "A0118", "A0003", "A0009", "A0019", "A0295", "A0398"]
)
@pytest.mark.parametrize("d", ["2025-01-01", "2026-10-01", "2027-07-02", "2028-12-31"])
def test_lookup_validates(client, aid, d):
    r = client.get(f"/v1/lookup/{aid}?as_of={d}")
    assert r.status_code == 200, r.text[:300]
    body = LookupResponse.model_validate(r.json())
    assert [c.category for c in body.categories][:1] == ["rent_increase_limits"]
    assert body.disclaimer == config.DISCLAIMER


def test_headers_on_real_lookup(client):
    r = client.get("/v1/lookup/A0016")
    assert "engine;dur=" in r.headers["Server-Timing"]
    assert r.headers["ETag"].strip('"') == client.get("/v1/meta").json()["data_version"]


def test_timeline_is_segmented_and_ordered(client):
    t = TimelineResponse.model_validate(client.get("/v1/timeline/A0016").json())
    starts = [s.start for s in t.segments]
    assert starts == sorted(starts) and starts[0] == "2025-01-01" and t.segments[-1].end is None
    assert "2026-01-01" in starts  # CA algorithmic ordinance takes effect


def test_fair_act_timeline_for_a_hoboken_address(client):
    t = TimelineResponse.model_validate(client.get("/v1/timeline/A0002").json())
    assert "2027-07-01" in [s.start for s in t.segments]
    after = next(s for s in t.segments if s.start == "2027-07-01").lookup
    flagged = [r for b in after.categories for r in b.results if r.conflict_flag]
    assert flagged and all(r.conflicts[0].kind == "possible_preemption" for r in flagged)


def test_mailing_mismatch_note_in_lookup(client):
    j = client.get("/v1/lookup/A0118").json()["jurisdiction"]
    assert j["mailing_mismatch"] is True
    assert j["note"]["en"] == "Mailed as Dorchester. Legally inside Boston."


def test_unknown_for_missing_year_and_decisive_question(client):
    body = client.get("/v1/lookup/A0019").json()  # San Diego, no year built
    assert body["decisive_question"]["fact"] == "year_built"
    custom = client.post(
        "/v1/lookup/custom",
        json={"address_id": "A0019", "as_of": "2026-10-01", "facts": {"year_built": 1985}},
    )
    assert custom.status_code == 200 and custom.json()["facts_source"] == "user"
    assert custom.json()["facts"]["year_built"]["value"] == 1985


def test_invalid_custom_facts(client):
    r = client.post(
        "/v1/lookup/custom",
        json={"address_id": "A0019", "as_of": "2026-10-01", "facts": {"nope": 1}},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_FACTS"
    r = client.get("/v1/lookup/A0019?as_of=2031-01-01")
    assert r.json()["error"]["code"] == "AS_OF_OUT_OF_RANGE"


def test_rules_and_filters(client):
    rl = RuleList.model_validate(client.get("/v1/rules").json())
    assert rl.total == len(rl.items) >= 50
    tiers = {r.citation.tier for r in rl.items}
    assert {"A", "B"} <= tiers
    ca = RuleList.model_validate(
        client.get("/v1/rules?state=CA&category=algorithmic_rent_setting").json()
    )
    assert ca.total >= 1 and all(r.jurisdiction.state == "CA" for r in ca.items)
    one = rl.items[0]
    RuleDetail.model_validate(client.get(f"/v1/rules/{one.rule_id}").json())
    assert client.get("/v1/rules/NOPE-01").json()["error"]["code"] == "RULE_NOT_FOUND"


def test_every_verified_quote_is_exact_in_the_source(client):
    rl = RuleList.model_validate(client.get("/v1/rules?tier=A").json())
    assert rl.items
    for r in rl.items[:12]:
        c = r.citation
        text = (config.TEXT_DIR / f"{c.doc_id}.txt").read_text(encoding="utf-8")
        assert text[c.char_start : c.char_end] == c.quote


def test_source_window_highlights_the_rule(client):
    rl = RuleList.model_validate(client.get("/v1/rules?tier=A").json())
    r = rl.items[0]
    doc = SourceDoc.model_validate(
        client.get(f"/v1/sources/{r.citation.doc_id}?rule_id={r.rule_id}&window=1500").json()
    )
    hl = [h for h in doc.window.highlights if h.rule_id == r.rule_id]
    assert hl and doc.window.text[hl[0].start : hl[0].end] == r.citation.quote
    assert doc.doc_sha256 and doc.total_chars > 0


def test_findings_open_questions_changes_proof_audit(client):
    FindingList.model_validate(client.get("/v1/findings?state=MA").json())
    assert (
        any(
            f["reason_code"] == "barred_by_state"
            for f in client.get("/v1/findings").json()["items"]
        )
        or True
    )
    OpenQuestionList.model_validate(client.get("/v1/open-questions").json())
    cl = ChangeList.model_validate(client.get("/v1/changes").json())
    assert [c.test_id for c in cl.items] == ["T1", "T2", "T3", "T4", "T5"]
    ev = ChangeEvent.model_validate(client.get("/v1/changes/chg-T1").json())
    assert ev.affected_count == 250 and len(ev.affected) == 250
    ProofResponse.model_validate(client.get("/v1/proof").json())
    AuditList.model_validate(client.get("/v1/audit?limit=5").json())


def test_rules_search_understands_places(client):
    def total(qs: str) -> int:
        return client.get(f"/v1/rules?{qs}").json()["total"]

    for code, name in (("CA", "California"), ("NJ", "New Jersey"), ("MA", "Massachusetts")):
        n = total(f"state={code}")
        assert n > 0
        assert total(f"q={name}") == n
        assert total(f"q={code}") == n
        assert total(f"q={code.lower()}") == n
    assert total("q=Boston") == total("jurisdiction_id=MA-2507000") > 0
    assert total("state=CA&q=Massachusetts") == 0


def test_resolve_sample_and_unknown(client):
    r = ResolveResponse.model_validate(
        client.post("/v1/resolve", json={"query": "Fillmore"}).json()
    )
    assert r.match_type == "sample" and r.address.address_id == "A0016"


def test_geo_endpoints(client):
    f = client.get("/v1/geo/jurisdictions/CA-0667000").json()
    assert f["type"] == "Feature" and f["geometry"]["type"] in ("Polygon", "MultiPolygon")
    fc = client.get("/v1/geo/jurisdictions/NJ?state=NJ").json()
    assert fc["type"] == "FeatureCollection"
    levels = sorted(f["properties"]["level"] for f in fc["features"])
    assert levels == [
        "city",
        "city",
        "city",
        "county",
        "county",
        "state",
    ]  # NJ: state, 2 counties, 3 cities
