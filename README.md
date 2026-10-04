<div align="center">

# Tenantly

**The housing law that reaches your door — cited, dated, and checked against your building.**

Address in. Every applicable rent-increase, eviction, deposit, fee, screening, and algorithmic rent-setting rule out — each quoted word-for-word from the statute, with its source, retrieval date, and an honest account of what we could and couldn't verify.

[![Live App](https://img.shields.io/badge/Live_App-tenantlyrent.me-4F46E5?style=for-the-badge)](https://tenantlyrent.me)
[![API Docs](https://img.shields.io/badge/API_Docs-api.tenantlyrent.me/docs-059669?style=for-the-badge)](https://api.tenantlyrent.me/docs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

*Information, not legal advice.*

</div>

---

> **For judges.** The live Ingest page is open: paste a law, extract, review, and publish with no login. The API's self-test endpoint returns measured scores in real time at [`/v1/proof`](https://api.tenantlyrent.me/v1/proof). Source files are at [`/v1/submission/rules.json`](https://api.tenantlyrent.me/v1/submission/rules.json), [`/v1/submission/lookups.json`](https://api.tenantlyrent.me/v1/submission/lookups.json), and [`/v1/submission/changes.json`](https://api.tenantlyrent.me/v1/submission/changes.json). If you call the API on a locked host, send `X-Admin-Token: tenantly-demo`.

---

## Contents

1. [The problem](#1-the-problem)
2. [What Tenantly does](#2-what-tenantly-does)
3. [Results](#3-results)
4. [How it works](#4-how-it-works)
5. [Architectural decisions](#5-architectural-decisions)
6. [Honesty by design](#6-honesty-by-design)
7. [Reproduce everything](#7-reproduce-everything)
8. [Outputs](#8-outputs)
9. [API reference](#9-api-reference)
10. [Repository map](#10-repository-map)
11. [Deployment](#11-deployment)
12. [Limitations](#12-limitations)
13. [Where this goes](#13-where-this-goes)
14. [Credits and licenses](#14-credits-and-licenses)

---

## 1. The problem

Rental housing in the U.S. is regulated in layers — state statutes, city ordinances, and pending bills — each with its own coverage tests (building age, unit count, owner type), effective dates, and exemptions. Whether a rule applies to *one apartment* depends on its exact legal location and the date you ask. Both are easy to get wrong:

- **A mailing city is not a legal city.** 37 of our 110 Massachusetts sample buildings are mailed as Dorchester, Roxbury, Allston, and other neighborhoods. Legally they are all in Boston.
- **Enacted is not in effect.** New Jersey's FAIR Act was signed July 20, 2026, but takes effect July 1, 2027. The statute never says "July 1, 2027" — it says "the first day of the twelfth month next following the date of enactment."
- **Proposed is not law, and struck is not law.** Massachusetts has pending algorithmic-pricing bills and a rent-control ballot question struck by the state's high court. A tool that reports them as rules actively misleads renters.
- **Public records are incomplete.** 212 of the 500 sample buildings have no year built on file, and owner type is never public. The honest answer is often "we can't tell from public data" — paired with the one fact that would settle it.

Renters can't afford to get this wrong. Small landlords can't afford lawyers. Advocates can't see across jurisdictions. The source text is public but scattered, unstructured, and constantly changing.

---

## 2. What Tenantly does

Built for the RealPage *Rental Housing Law Navigator* challenge: **3 states · 10 cities · 6 rule categories · 500 real buildings · 87 source documents**.

| For a renter | For an advocate or agency | For a small housing provider |
|---|---|---|
| Type an address, see every applicable rule per category, what starts later, and what is only proposed | Pick a law change, see which buildings it reaches — before and after | Coverage conditions and exemptions spelled out in the law's own words |
| Read the exact quoted sentence behind every answer, with retrieval date | Conflict flags where state and local law may collide | The same evidence a lawyer would start from — never advice, never ways around a rule |
| Plain English, accessible design | CSV-ready change sets and a full audit log | Email or Atom-feed watch alerts when a law affecting that building changes |

### Feature summary

| Feature | Status |
|---|---|
| **Rule extraction** (Module A) — automated, no hand-coding | ✅ 84 rules extracted, 100% byte-verified quotes |
| **Address lookup** (Module B) — with cited jurisdicton stack | ✅ 500 addresses, all 6 rule categories |
| **Change tracking** (Module C) — T1–T6, as-of date query | ✅ All tests passing |
| **Bitemporal date slider** — instant, no network round-trip | ✅ Precomputed timelines |
| **Plain-language summaries** | ✅ English; reading grade 9.5 |
| **Confidence scores and conflict flags** | ✅ Per rule and per answer |
| **Live law ingestion** — paste a URL or text, extract, review, publish | ✅ SSE progress, human Publish/Reject step |
| **Autonomous extraction judge** — re-runs adjudicator on demand | ✅ `/v1/ingest/{id}/rejudge` |
| **Email watch alerts** — notifies subscribers when affecting law changes | ✅ Via Resend; degrades gracefully if key absent |
| **Atom feed and ICS calendar** per address | ✅ `/v1/alerts/feed/{id}.atom`, `/v1/alerts/calendar/{id}.ics` |
| **Law Watch** — scans official sources on a schedule | ✅ Allow-listed sources only; staged, never auto-published |
| **Stretch: confidence + conflict** | ✅ Evidence tiers A/B/C/C1 |
| **Stretch: extend to new jurisdiction live** | ✅ Rehearsed on fictional Cambridge ordinance (T6 fixture) |

### System architecture

![Tenantly system architecture: law compiler, address resolver, rules engine, API, web app, ingestion path](docs/system-architecture.jpg)

### User flow

![Tenantly user flow: address input to cited answer, the as-of date slider, decisive-question card, and change tracking view](user-flow.png)

---

## 3. Results

All values are measured; see `artifacts/eval/` and the live [Proof page](https://tenantlyrent.me/proof).

### Self-score (mirrors the published rubric)

| Component | Max | Self-score |
|---|---|---|
| Extraction accuracy | 25 | **25.0** |
| Address coverage | 20 | **17.5** |
| Citations | 15 | **14.8** |
| Change tracking | 15 | **15.0** |
| **Total (auto-graded)** | **75** | **72.3** |

### Change tests

| Test | What it checks | Result |
|---|---|---|
| T1 | CA AB 325 / SB 763 — `2025-12-31 → 2026-01-02` | 250 CA buildings; "not yet effective" flips to "applies" ✓ |
| T2 | Hoboken vs. Jersey City local bans — neither bleeds into Newark | 40 + 50 = 90 affected; 0 in Newark ✓ |
| T3 | NJ FAIR Act — signed 2026-07-20, effective 2027-07-01; possible preemption | 140 affected; 90 conflict flags ✓ |
| T4 | MA S.2983 / H.5222 (pending bills) — never enacted | 110 MA addresses; reported as `pending`, never `applies` ✓ |
| T5 | MA rent-control ballot question — struck 2026-06-23 | 0 affected; recorded as `failed` ✓ |
| T6 | Hour-16 fictional Cambridge ordinance | Ingest path rehearsed on fixture; extracted, correct effective date ✓ |

### Integrity and performance

| Metric | Value |
|---|---|
| Rules extracted (Tier A / B / C / C1) | 25 / 59 / 4 / 1 = **89 total** |
| Tier A/B quotes verified byte-for-byte | 84 / 84 — **100%** |
| Candidate rules rejected (quote not in source) | 498 |
| Buildings resolved by geometry | 499 |
| Mailing-city mismatches caught | 37 |
| Suspect ZIPs dropped before geocoding | 83 |
| Unit counts recovered from public descriptions | 90 |
| Contradicting public records flagged | 12 |
| Mean reading grade of renter summaries | 9.48 |
| Lookup latency p50 / p95 (server) | 7.8 ms / 15.3 ms |
| Retrieval + LLM baseline (same question) | 6.4 s |
| Total model spend to compile corpus | $3.61 of a $6.00 cap |

---

## 4. How it works

Tenantly is a **law compiler**, not a chatbot. Models read the law once, at compile time, into a verified, time-aware rule graph. Answering an address query is deterministic code over that graph — no model call on the lookup path.

```
flowchart LR
  87 sources → Load (hash verify, boilerplate mask, version segments)
            → Extract (2 independent Claude Sonnet passes + Haiku cross-check)
            → Verify (byte-exact quotes at recorded offsets)
            → Adjudicate (Claude Opus, disagreements only, must cite span)
            → Legal calendar (code computes dates from expressions)
            → Evidence tiers + gap audit + precedence
            → Rule graph

  500 buildings → Facts with intervals + provenance
               → Geocode → point-in-polygon on Census TIGER boundaries
               → Resolved buildings

  Rule graph + Resolved buildings → Three-valued engine over time
                                  → Precomputed timelines
                                  → rules.json · lookups.json · changes.json
                                  → API + app + static fallback

  Law Watch (every 6h) → same DAG → staged overlay → human review
```

### Compile time (~8 minutes, ~$3.61; cached reruns cost near zero)

1. **Load** — Verify each document's SHA-256 against the manifest. Mask web boilerplate *without* changing byte offsets. Split statutes containing multiple versions (`"effective until August 1, 2025"` / `"effective August 1, 2025"`) into dated segments.
2. **Extract** — Two independent Claude Sonnet passes (section view + whole-document view) plus a Claude Haiku cross-check. Disagreements go to a Claude Opus adjudicator that must cite the deciding span.
3. **Verify** — Every quoted span must be an exact substring of the raw source at recorded offsets. Anything else is rejected (498 candidates rejected in this run).
4. **Compute dates** — Models extract date *expressions*; code computes the final dates. Example: `"first day of the twelfth month next following the date of enactment"` + `"approved July 20, 2026"` → **2027-07-01**.
5. **Audit gaps** — A 13 × 6 jurisdiction-by-category matrix is fully accounted for: every cell holds either a rule or a reasoned "no rule at this level" (barred by state law, motion-only, pending, failed, text not supplied).
6. **Link** — Precedence and conflicts become explicit graph edges with quoted evidence (e.g., SF rent cap supersedes the state AB 1482 cap; NJ FAIR Act may preempt the Jersey City and Hoboken municipal bans).

### Query time (milliseconds, zero model calls)

1. **Resolve** the building's legal city by point-in-polygon on Census TIGER boundaries — incorporated places in California, county subdivisions in New Jersey and Massachusetts. Never by mailing city.
2. **Evaluate** each rule's coverage with three-valued Kleene logic over interval facts.
3. **Serve** a precomputed timeline. Moving the date slider requires no network request.

---

## 5. Architectural decisions

| Decision | Typical approach | Tenantly | Why it matters |
|---|---|---|---|
| **Where models run** | Every query | Compile and ingest only | Millisecond answers; no query-time hallucination; reproducible outputs |
| **Citations** | Model-written | Byte-exact spans verified at recorded offsets | Citation validity is a system property, not a hope |
| **Dates** | Model guesses | Deterministic legal calendar | The rules most likely to be misdated are dated correctly |
| **Missing facts** | Guess, or treat as false | Kleene logic over intervals: `unknown` is computed, explained, and paired with the one question that resolves it | Honest coverage without invented answers |
| **Building facts** | Use raw cell value | Derive with provenance; intersect sources; flag contradictions | Recovers unit counts parcel data left blank |
| **Jurisdiction** | Postal city string | Census TIGER geometry, right layer per state; suspect ZIPs dropped first | Dorchester → Boston; San Ysidro → San Diego; 83 owner-mailing ZIPs in NJ neutralized |
| **Time** | Re-query per date | Bitemporal timelines precomputed per building | Instant date slider; change tracking is a diff, not a recomputation |
| **Orchestration** | Free-roaming agents | Deterministic, content-addressed DAG; bounded agents with forced tool outputs | Predictable cost, replayable runs, a demo that cannot fail |
| **Gaps in sources** | Silence or invention | Evidence tiers (§6) | Honest coverage of laws whose text wasn't supplied |
| **New law** | Overwrite | Staged overlay + blast-radius preview + human Publish/Reject; Law Watch opens pull requests | Humans approve what renters see |

---

## 6. Honesty by design

### Evidence tiers

Every rule carries a tier, visible in the app and in `conflict_note`:

| Tier | Meaning | Quote source |
|---|---|---|
| **A** | Official law text supplied in the corpus | Corpus, byte-verified |
| **B** | Official agency page in the corpus describing the law | Corpus, byte-verified |
| **C** | Law text *not supplied* (link-only); confirmed by ≥2 independent supplied signals | Named supplementary doc, verbatim. **Never invented.** Confidence ≤ 0.6 |
| **C1** | Only one signal | Same as C; result always `unknown` |

### What we surfaced automatically (open questions)

- Berkeley's algorithmic-pricing ordinance has two published effective dates; both precede the query date so the answer is unaffected, and we say so.
- Los Angeles's RSO published increase (3%) was valid only through June 30, 2026; the current figure is not in our sources for an October 2026 query.
- California's screening-fee cap has no single official 2026 figure (the statute says $30 adjusted for CPI; Berkeley Rent Board publishes $68.96).
- New Jersey's FAIR Act may preempt the Jersey City and Hoboken ordinances from July 1, 2027; those buildings carry a conflict flag for human review.

### Guardrails

- **Never legal advice.** Every screen says so, every API response carries the disclaimer.
- **Never invent.** No facts, dates, URLs, scores, or latency numbers are hand-written. `"Unknown"` means `null`.
- **Never guess dates.** Effective-date computation is deterministic code, not a prompt.
- **Audit trail.** Every model call is logged with model, prompt version, input/output hashes, verifier result, and cost (`artifacts/audit/compile_audit.jsonl`).
- **Eval isolation.** `eval/silver_key.yaml` is enforced by `tests/test_integrity.py` to never be imported by `engine/`. That test cannot be weakened.

---

## 7. Reproduce everything

```bash
git clone https://github.com/Esh90/Tenantly.git && cd Tenantly
# Place the starter pack in dataset/ (read-only) and dataset_supplement/
make setup                          # uv sync + .env scaffold
echo "ANTHROPIC_API_KEY=sk-..." >> .env
# Optional: email watch alerts
echo "RESEND_API_KEY=re_..." >> .env
echo "ALERT_FROM=Tenantly <alerts@tenantlyrent.me>" >> .env
make compile ARGS=--explain         # preview stages and cost before spending
make all                            # compile → geo → resolve → lookups → timelines → changes → export → score → snapshot
make test                           # full suite: traps, T1–T5, contract, integrity
make serve                          # API at http://localhost:8000/docs
```

**Re-runs are deterministic.** Every compile stage is content-addressed; the same inputs produce the same outputs without new model calls.

**Live ingest.** `make ingest-file FILE=<path>` runs the full pipeline on any new document, as in the live demo. Or use the Ingest tab at [tenantlyrent.me/ingest](https://tenantlyrent.me/ingest).

---

## 8. Outputs

| File | Contents | Validated by |
|---|---|---|
| [`out/rules.json`](out/rules.json) | 89 rule records in the official schema (including pending and failed measures) | JSON Schema draft 2020-12 |
| [`out/lookups.json`](out/lookups.json) | All 500 addresses as of 2026-10-01; result ∈ `applies` / `unknown` / `superseded` / `not_yet_effective` / `pending` | `tests/test_export.py` |
| [`out/changes.json`](out/changes.json) | Affected and conflict-flagged address sets for T1–T6 | `tests/test_changes.py` |
| [`METHOD_NOTE.md`](METHOD_NOTE.md) | One-page method note generated from artifacts | `make method-note` |

---

## 9. API reference

OpenAPI docs: [`https://api.tenantlyrent.me/docs`](https://api.tenantlyrent.me/docs)

| Endpoint | Purpose |
|---|---|
| `GET /v1/lookup/{address_id}?as_of=YYYY-MM-DD` | Full answer for one building on one date |
| `GET /v1/timeline/{address_id}` | Every dated segment (powers the instant date slider) |
| `POST /v1/lookup/custom` | Re-evaluate with user-supplied facts, labeled "based on what you told us" |
| `GET /v1/sources/{doc_id}?rule_id=` | Source text with the quoted span highlighted |
| `GET /v1/changes/{id}` | Before/after rule set per affected building |
| `POST /v1/ingest` | Compile a new law into a staged overlay (public; no token in demo mode). Progress via SSE. |
| `POST /v1/ingest/{id}/publish` | Human-approve an overlay |
| `POST /v1/ingest/{id}/rejudge` | Re-run the autonomous adjudicator judge |
| `POST /v1/alerts/subscriptions` | Watch an address for law changes (email via Resend, server-side only) |
| `GET /v1/alerts/feed/{address_id}.atom` | Atom feed for an address |
| `GET /v1/alerts/calendar/{address_id}.ics` | ICS calendar for an address |
| `GET /v1/submission/{rules\|lookups\|changes}.json` | Submission files served directly |
| `GET /v1/proof` | Measured scores, verification stats, latency, cost, open questions |
| `GET /v1/audit` | Compile audit log (model, prompt version, hashes, verifier, cost per call) |

Every response includes `Server-Timing`, `data_version`, `as_of`, `sources_retrieved_at`, `is_projection`, and `disclaimer`.

**Demo ingest token** (if `PUBLIC_INGEST_ENABLED=false` on a private deployment):

```http
X-Admin-Token: tenantly-demo
```

---

## 10. Repository map

```
engine/
  corpus/     document loading, boilerplate masking, version segments, doc types
  compile/    the DAG, model calls (cache + ledger + audit), verifier, legal calendar, evidence tiers
  geo/        Census geocoding, TIGER boundaries, point-in-polygon
  facts/      use-code derivations, intervals, record conflicts
  rules/      three-valued engine, precedence, timelines, change tests
  export/     submission files, static snapshot, method note
  api/        FastAPI service (routers, SSE, error envelope, deps)
  watch/      Law Watch agent, Resend email alerts, Atom/ICS feeds
frontend/     React 19 + Vite + TanStack Router + MapLibre + shadcn/ui
eval/         self-scorer and silver key (never read by engine/)
tests/        traps, change tests, contract, integrity
out/          rules.json · lookups.json · changes.json (submission outputs)
artifacts/    compiled rules, resolved addresses, audit logs, eval results
```

---

## 11. Deployment

### Quick deploy (backend on Render, frontend on Vercel)

**Backend — Render**

1. Fork/clone and push to GitHub.
2. In the [Render dashboard](https://dashboard.render.com), click **New → Blueprint** and select this repo. Render reads `render.yaml` and creates a Docker web service automatically.
3. Add secrets in Render → Environment:
   - `ANTHROPIC_API_KEY` — your Anthropic key
   - `ADMIN_TOKEN` — choose a token (or leave `tenantly-demo` for a public demo)
   - `RESEND_API_KEY` — optional, enables email watch alerts
   - `ALERT_FROM` — e.g. `Tenantly <alerts@tenantlyrent.me>`
4. After the first deploy, go to **Settings → Custom Domain** and add `api.tenantlyrent.me`.

**Frontend — Vercel**

1. In [Vercel](https://vercel.com), click **Add New → Project** → import this repo.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Vite** (auto-detected).
4. Add environment variable:
   - `VITE_API_BASE_URL` = `https://api.tenantlyrent.me`
5. Deploy. Then go to **Settings → Domains** and add `tenantlyrent.me`.

**DNS on Namecheap (Advanced DNS tab)**

| Type | Host | Value | TTL |
|---|---|---|---|
| `A` | `@` | `76.76.21.21` | Automatic |
| `CNAME` | `www` | `cname.vercel-dns.com` | Automatic |
| `CNAME` | `api` | `<your-service>.onrender.com` | Automatic |

Replace `<your-service>` with the `.onrender.com` subdomain shown in your Render service dashboard.

---

## 12. Limitations

- **Coverage** — 3 states and 10 cities per the challenge scope. County ordinances are out of scope.
- **Unsupplied texts** — Jersey City and Hoboken algorithmic bans, Santa Ana's ban, and some Newark and Hoboken municipal code pages were link-only in the corpus. They appear as Tier C/C1 with explicit labels.
- **Year-built proxy** — Year built stands in for certificate-of-occupancy date; buildings in a cutoff year are `unknown`.
- **Owner facts** — Owner type and subsidy status are not public. Exemptions that depend on them are shown as caveats or `unknown`.
- **Retrieval date** — Sources were retrieved October 1, 2026. Answers for later dates are labeled as projections. Law Watch is how this stays current.
- **Scoring** — The self-score uses our silver key, not the organizers' held-out key.

---

## 13. Where this goes

- **The thesis.** Housing law is a fast-changing, address-keyed dataset that nobody maintains as data. Tenantly compiles it once, verifies every claim, and keeps it current with a change feed that says *which buildings* each new law touches.
- **Why the design extends.** Adding a city means adding documents and a boundary identifier and running one command. Law Watch keeps the graph current at near-zero cost when nothing changes. Every new rule passes the same quote verification and human review.
- **Who it can serve.** Free renter answers and legal-aid tooling · an API for cities, housing agencies, and research groups that need address-level coverage maps · compliance-awareness feeds for small housing providers — always informational, never a certification.
- **Near-term milestones.** Expand to the 14 jurisdictions with algorithmic rent-setting bans · add county layers · open-source the verified rule dataset as a public good, with partners, as the challenge brief invites.

---

## 14. Credits and licenses

Built at the **Hack-Nation 7th Global AI Hackathon** · October 3–4, 2026 · for RealPage's **Challenge 02: Rental Housing Law Navigator**.

- **Data** — Starter pack: public statutes, ordinances, and agency pages; public assessor parcel records. U.S. Census Bureau Geocoder and TIGER/Line (public domain). Map data © OpenStreetMap contributors, via OpenFreeMap / OpenMapTiles.
- **Models** — Anthropic Claude (Haiku 4.5, Sonnet 5.5, Opus 5.5), at compile time only.
- **Email alerts** — [Resend](https://resend.com).
- **Code** — MIT License. See [LICENSE](LICENSE).

---

*Tenantly displays public housing law for information only. It is not legal advice. Verify with the official source or a qualified professional before acting.*
