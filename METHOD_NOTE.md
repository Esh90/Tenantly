# Tenantly: method note

*Information, not legal advice.*

## Problem
Which housing rules apply to one apartment on a given date? Rules come from state statutes, city
ordinances and pending bills; each has coverage tests (building age, unit count, owner type),
effective dates and exemptions, and the answer depends on the building's legal city and the date.

## Pipeline
1. **Compile the law, offline.** Each of the 54 supplied documents is read in two
   passes (Claude Sonnet by section, Claude Haiku over the whole in-force text). Every quote must be an
   exact span of the source file at stored offsets, or the rule is discarded. Disagreements between the
   passes go to an adjudicator that must cite the deciding span. No model is called when an address is looked up.
2. **Dates are computed, not guessed.** The model reports date expressions; a deterministic legal calendar
   computes dates ("first day of the twelfth month next following enactment" gives 2027-07-01 for the FAIR Act).
3. **Facts with provenance.** Units and year built come from assessor records, with intervals (a 5-unit use code
   is [5, infinity)); when two records contradict, the fact is unknown and flagged.
4. **Jurisdiction by geometry.** Census TIGER boundaries and point-in-polygon decide the legal city; the
   mailing city never does.
5. **Three-valued logic.** Coverage and exemptions are predicates over a fixed fact registry, evaluated with
   TRUE / FALSE / UNKNOWN over intervals. Unknown is an answer, with the missing fact named.
6. **Precedence and change tracking.** State bars, local-over-state precedence and preemption conflicts are
   explicit relations with quoted evidence; timelines are precomputed per address, and change tests diff them.

## Evidence tiers
A: official law text in the corpus. B: official agency or bill page. C: a law whose text was not supplied but
that two independent supplied signals assert (the quote is supplementary text, labeled, never the ordinance).
C1: one signal; always unknown.

## Measured results
Self-score against our own silver key (the official scorer was not in the pack):

| Component | Score | Note |
|---|---|---|
| Extraction | 25.0 / 25 | 48 of 48 expected rules matched by jurisdiction, category and cite; mean field accuracy 1.00 |
| Address coverage | 17.5 / 20 | 30 of 32 address expectations exactly right; a missed 'applies' costs 2, unknown earns half |
| Citations | 14.8 / 15 | 6428 of 6518 'applies' answers cite a quote found at its stored offsets in the corpus (98.6%) |
| Change tracking | 15.0 / 15 | 5 of 5 tests match the expected sets exactly (Jaccard mean 1.00) |

Change tests (computed from resolved legal cities):

| Test | Affected | Conflict flags | Result |
|---|---|---|---|
| T1 | 250 (expected 250) | 0 (expected 0) | pass |
| T2 | 90 (expected 90) | 0 (expected 0) | pass |
| T3 | 140 (expected 140) | 90 (expected 90) | pass |
| T4 | 110 (expected 110) | 0 (expected 0) | pass |
| T5 | 0 (expected 0) | 0 (expected 0) | pass |

| Metric | Value |
|---|---|
| Rules extracted (Tier A / B / C / C1) | 25 / 54 / 4 / 1 |
| Tier A/B quotes verified byte-for-byte against the corpus | 82 of 82 (100%) (target 100%) |
| Candidate rules rejected because their quote wasn't in the source | 498 |
| Fields resolved by the adjudicator model | 1 |
| Buildings resolved by geometry / mailing-city mismatches caught | 499 / 37 |
| Suspect ZIP codes dropped before geocoding | 83 |
| Unit counts recovered from public-record descriptions | 90 |
| Public records that contradict each other (flagged, never guessed) | 12 |
| Mean reading grade of renter summaries (EN) | 9.72 (max 24.4; gate ≤ 8.5) |
| Total model spend to compile the corpus | $3.72 of a $6.00 cap |
| Lookup latency p50 / p95 (server) | 7.8 ms / 15.3 ms |
| Same question via retrieval + LLM (baseline) | 6.4 s |

## Limitations
- 87 rules were extracted; some guidance pages yield several near-duplicate records.
- Facts such as owner type are not public; the app asks one question and shows caveats instead of guessing.
- Answers after 2026-10-01 are projections from sources retrieved that day.
- One sample address (a parcel lot with no house number) could not be geocoded; its city rules are unknown.

## Not legal advice
Tenantly describes public law for information. Check the official source or a qualified professional before acting.
