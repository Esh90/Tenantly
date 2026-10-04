"""Every PLAN.md 14.4 endpoint returns the documented shape; errors use the envelope."""

import csv

import pytest

from engine import config
from engine.models import (
    AddressList,
    AddressSearch,
    AuditList,
    ChangeEvent,
    ChangeList,
    FindingList,
    Health,
    IngestAccepted,
    IngestJob,
    LookupResponse,
    Meta,
    OpenQuestionList,
    ProofResponse,
    PublishResult,
    ResolveResponse,
    RuleDetail,
    RuleList,
    SourceDoc,
    SubscriptionCreated,
    TimelineResponse,
    UpcomingChange,
)

ADMIN = {"X-Admin-Token": config.ADMIN_TOKEN}
CATS = {
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
}


def _ids():
    with open(config.ADDRESSES_CSV, newline="", encoding="utf-8") as fh:
        return [r["address_id"] for r in csv.DictReader(fh)]


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    Health.model_validate(r.json())


def test_meta(client):
    m = Meta.model_validate(client.get("/v1/meta").json())
    assert m.default_as_of == "2026-10-01"
    assert m.counts.addresses == 500
    assert m.counts.docs_text == 54 and m.counts.docs_link_only == 33
    assert {c.key for c in m.categories} == CATS
    assert m.disclaimer == config.DISCLAIMER


def test_addresses_cover_all_500_real_ids(client):
    body = AddressList.model_validate(client.get("/v1/addresses").json())
    assert [i.address_id for i in body.items] == _ids()


def test_search_and_resolve(client):
    s = AddressSearch.model_validate(client.get("/v1/addresses/search?q=fillmore&limit=3").json())
    assert s.items and len(s.items) <= 3
    r = ResolveResponse.model_validate(client.post("/v1/resolve", json={"query": "A0016"}).json())
    assert r.match_type == "sample" and r.address.address_id == "A0016"
    nf = ResolveResponse.model_validate(client.post("/v1/resolve", json={"query": "zzz"}).json())
    assert nf.match_type == "not_found"


def test_lookup_shape_and_disclaimer_fields(client):
    r = client.get("/v1/lookup/A0016?as_of=2026-10-01")
    body = LookupResponse.model_validate(r.json())
    assert [c.category for c in body.categories] == [
        "rent_increase_limits",
        "just_cause_eviction",
        "security_deposits",
        "application_screening_fees",
        "screening_restrictions",
        "algorithmic_rent_setting",
    ]
    assert body.disclaimer == config.DISCLAIMER
    assert body.sources_retrieved_at == "2026-10-01"
    assert body.is_projection is False
    assert body.facts_source == "data"


def test_lookup_after_retrieval_is_projection(client):
    body = LookupResponse.model_validate(client.get("/v1/lookup/A0016?as_of=2027-07-02").json())
    assert body.is_projection is True


def test_lookup_defaults_to_default_as_of(client):
    assert client.get("/v1/lookup/A0016").json()["as_of"] == "2026-10-01"


@pytest.mark.parametrize("bad", ["2024-12-31", "2029-01-01", "not-a-date"])
def test_as_of_out_of_range(client, bad):
    r = client.get(f"/v1/lookup/A0016?as_of={bad}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "AS_OF_OUT_OF_RANGE"


def test_unknown_address_envelope(client):
    r = client.get("/v1/lookup/A9999")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "ADDRESS_NOT_FOUND" and err["request_id"].startswith("req_")


def test_custom_lookup(client):
    ok = client.post(
        "/v1/lookup/custom",
        json={"address_id": "A0016", "as_of": "2026-10-01", "facts": {"year_built": 1985}},
    )
    assert ok.status_code == 200
    assert LookupResponse.model_validate(ok.json()).facts_source == "user"
    bad = client.post(
        "/v1/lookup/custom",
        json={"address_id": "A0016", "as_of": "2026-10-01", "facts": {"favorite_color": "red"}},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_FACTS"


def test_timeline(client):
    t = TimelineResponse.model_validate(client.get("/v1/timeline/A0016").json())
    assert t.range.start == "2025-01-01" and t.range.end == "2028-12-31"
    assert t.segments[0].start == "2025-01-01"


def test_geo(client):
    f = client.get("/v1/geo/jurisdictions/CA-0667000").json()
    assert f["type"] == "Feature"
    fc = client.get("/v1/geo/jurisdictions/CA?state=NJ").json()
    assert (
        fc["type"] == "FeatureCollection" and len(fc["features"]) == 4
    )  # the state plus Jersey City, Hoboken, Newark
    assert client.get("/v1/geo/jurisdictions/nope").status_code == 404


def test_rules_findings_open_questions(client):
    rl = RuleList.model_validate(client.get("/v1/rules?state=CA").json())
    assert rl.total == len(rl.items)
    assert RuleList.model_validate(client.get("/v1/rules?state=NJ").json()).total == 0
    RuleDetail.model_validate(client.get("/v1/rules/CA-ALG-01").json())
    assert client.get("/v1/rules/NOPE").json()["error"]["code"] == "RULE_NOT_FOUND"
    FindingList.model_validate(client.get("/v1/findings?state=CA").json())
    OpenQuestionList.model_validate(client.get("/v1/open-questions").json())


def test_sources_real_document(client):
    d = SourceDoc.model_validate(client.get("/v1/sources/D022?window=500").json())
    assert d.total_chars > 500 and len(d.window.text) == 500
    assert d.doc_sha256 and len(d.doc_sha256) == 64
    link_only = SourceDoc.model_validate(client.get("/v1/sources/D002").json())
    assert link_only.total_chars == 0 and link_only.doc_sha256 is None
    assert client.get("/v1/sources/D999").json()["error"]["code"] == "DOC_NOT_FOUND"


def test_changes(client):
    cl = ChangeList.model_validate(client.get("/v1/changes").json())
    assert [c.test_id for c in cl.items] == ["T1", "T2", "T3", "T4", "T5"]
    ev = ChangeEvent.model_validate(client.get("/v1/changes/chg-T1").json())
    assert ev.test_type == "as_of"
    assert client.get("/v1/changes/nope").json()["error"]["code"] == "CHANGE_NOT_FOUND"


@pytest.mark.parametrize("name", ["rules", "lookups", "changes"])
def test_submission_files(client, name):
    assert client.get(f"/v1/submission/{name}.json").status_code == 200


def test_ingest_requires_admin(client):
    r = client.post("/v1/ingest", json={"title": "t", "text": "x"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_ingest_flow(client):
    acc = client.post("/v1/ingest", json={"title": "t", "text": "ordinance text"}, headers=ADMIN)
    assert acc.status_code == 202
    a = IngestAccepted.model_validate(acc.json())
    job = IngestJob.model_validate(client.get(f"/v1/ingest/{a.job_id}").json())
    assert job.status == "ready"
    ev = client.get(a.events_url)
    assert ev.status_code == 200
    assert "event: stage" in ev.text and "event: impact" in ev.text and "event: done" in ev.text
    pub = client.post(f"/v1/ingest/{a.job_id}/publish", headers=ADMIN)
    PublishResult.model_validate(pub.json())
    again = client.post(f"/v1/ingest/{a.job_id}/publish", headers=ADMIN)
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_PUBLISHED"
    assert client.get("/v1/ingest/job-nope").json()["error"]["code"] == "JOB_NOT_FOUND"


def test_ingest_too_large(client):
    r = client.post("/v1/ingest", json={"title": "t", "text": "x" * 200_001}, headers=ADMIN)
    assert r.status_code == 413 and r.json()["error"]["code"] == "DOCUMENT_TOO_LARGE"


def test_alerts(client):
    r = client.post(
        "/v1/alerts/subscriptions",
        json={"email": "a@example.com", "address_id": "A0016", "lang": "en"},
    )
    assert r.status_code == 201
    SubscriptionCreated.model_validate(r.json())
    assert "<feed" in client.get("/v1/alerts/feed/A0016.atom").text
    assert "BEGIN:VCALENDAR" in client.get("/v1/alerts/calendar/A0016.ics").text
    assert client.delete("/v1/alerts/subscriptions/tok").status_code == 204


def test_proof_and_audit(client):
    ProofResponse.model_validate(client.get("/v1/proof").json())
    AuditList.model_validate(client.get("/v1/audit?limit=5").json())


def test_headers(client):
    r = client.get("/v1/meta")
    assert r.headers["X-Request-Id"].startswith("req_")
    assert (
        "engine;dur=" in r.headers["Server-Timing"] and "total;dur=" in r.headers["Server-Timing"]
    )
    assert r.headers["ETag"] == '"fixture0"'
    assert r.headers["Cache-Control"] == "public, max-age=300, stale-while-revalidate=86400"
    assert client.get("/v1/health").headers["Cache-Control"] == "no-store"


def test_bad_request_uses_envelope(client):
    r = client.post("/v1/resolve", json={})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_upcoming_change_serializes_from_key():
    u = UpcomingChange.model_validate(
        {
            "date": "2026-01-01",
            "rule_id": "X",
            "title": "t",
            "from": "none",
            "to": "applies",
            "summary": {"en": "a", "es": "b"},
        }
    )
    assert u.model_dump(by_alias=True)["from"] == "none"
