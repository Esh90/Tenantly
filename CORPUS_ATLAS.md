# CORPUS_ATLAS.md: Tenantly's map of the starter pack

This is a careful reading of the RealPage starter pack (`participant-final-no-hour16`). It grounds every design decision in PLAN.md and is the source for our evaluation fixtures.

**Status of this document.** It is a human-and-model reading of the supplied files, not an official answer key. Where we are unsure, we say so (confidence: high, medium, low). The rule inventory in §6 becomes `eval/silver_key.yaml`. That file is used **only** to measure our pipeline. The extraction pipeline must never read it; `tests/test_integrity.py` enforces this.

---

## 1. Pack inventory

| Path | What it is | Notes |
|---|---|---|
| `README.md` | Participant guide | Defines the default query date (**2026-10-01**), the result values, the submission formats, the data gaps, and four "known open questions" (bonus if surfaced) |
| `mit-…-participant-no-scoring-no-hour16.pdf` | 6-page discussion-draft brief | Adds two expectations: "Audit view showing the source, retrieval date, as-of date and reasoning boundary for each answer", and a "one-page method note" in the submission package |
| `corpus/corpus_manifest.csv` | 87 rows | Columns: `doc_id, jurisdictions, url, source_type, capture, retrieved_at, sha256, text_file, status` |
| `corpus/text/D###.txt` | 54 plain-text documents (~690 KB total) | Each file starts with `SOURCE: <url>` and `RETRIEVED: 2026-10-01 HH:MM UTC`, then a blank line |
| `corpus/links_only.csv` | 33 sources with no supplied text | Law-firm/news pages, code publishers with "check-terms", and one official page that returned 403 (D056) |
| `data/sample_addresses.csv` | 500 rows, `A0001`–`A0500` | Columns: `address_id, street_address, postal_city, state, zip, year_built, units, use_code, use_description, source_dataset, retrieved_at` |
| `schema/rule_record.schema.json` | JSON Schema (draft 2020-12) | The official rule record format |
| `schema/sample_rule_record.json` | One worked example | NJ security deposit, cites a Justia URL (link-only D063) |
| `dev/change_tests.json` | T1–T5 definitions | Typed tests: `as_of`, `boundary`, `pending`, `negative` |
| `submission_templates/` | `rules.json`, `lookups.json`, `changes.json` | Exact output shapes |

**Not in the pack.**
- No dev answer key and no `score.py`. This is the "no-scoring" edition, so we build our own scorer (PLAN.md §16).
- No hour-16 document. PLAN.md Phase 6 handles it if released.
- The public 6-page challenge brief (the version listing "Jersey City §218-12 (Jun 2025)", "Hoboken ch. 158, Art. II (Jul 2025)", "Santa Ana Ord. NS-3090 (Apr 2026)") is **not** in the pack. The builder saves it as `dataset_supplement/challenge_brief_public.pdf` (it is the `REALPAGE.pdf` the team received).

---

## 2. Official formats (from schema and templates; these are law for our exporter)

**Rule record** (`rules.json` is `{"rules": [ … ]}`)
- Required fields: `team_rule_id, jurisdiction, level, category, status, title, requirement, citation, source_url, quoted_span`.
- Optional fields: `key_value, coverage_conditions, exemptions, overrides, interaction, effective_date, source_doc_id, confidence, conflict_flag, conflict_note`.

| Field | Allowed values / format |
|---|---|
| `jurisdiction` | `"CA" \| "NJ" \| "MA"`, or `"City, ST"` (e.g. `"San Francisco, CA"`) |
| `level` | `state \| city` (no county) |
| `category` | `rent_increase_limits, just_cause_eviction, security_deposits, application_screening_fees, screening_restrictions, algorithmic_rent_setting` |
| `status` | `in_force, not_yet_effective, pending, failed`, evaluated as of 2026-10-01 |
| `effective_date` | pattern `^\d{4}(-\d{2}(-\d{2})?)?$`, so year-only and year-month precision are legal |
| `quoted_span` | minimum 20 characters; "exact text copied from the source document" |
| `confidence` | 0–1 |
| `overrides` | `team_rule_id`s this rule supersedes or yields to; the direction goes in `interaction` |

**`lookups.json`**
```json
{"as_of": "2026-10-01", "lookups": {"A0001": [{"team_rule_id": "...", "result": "applies", "explanation": "...", "conflict_flag": false}]}}
```
- `result` ∈ `applies, unknown, superseded, not_yet_effective, pending`.
- All 500 addresses must be present.
- "Leave out rules that don't apply."

**`changes.json`**
```json
{"T1": {"affected_address_ids": [], "conflict_flag_address_ids": [], "notes": "..."}}
```
One key per test. Affected sets are computed over all 500 addresses.

**Scoring we optimize for** (public brief):
- Automatic: extraction 25, address coverage 20, citations 15, change tracking 15.
- Judged: plain language 10, responsible design 10, scalability 5.
- Matching is by **jurisdiction + category + citation**, so our ids don't need to match theirs.
- Missing an `applies` costs double; `unknown` earns partial credit.

---

## 3. Corpus mechanics (what the parser must handle)

1. **Header.** Lines 1–2 are `SOURCE:` and `RETRIEVED:`. The manifest is authoritative for URL, retrieval timestamp and sha256. Verify the sha256 of each text file at load. If a hash differs, record `hash_mismatch` in the audit and continue.
2. **Web boilerplate.** Navigation menus, cookie text, "Skip to main content", sign-in modals (malegislature.gov), and city site menus (D036 is mostly a Jersey City navigation tree). Strip it for model input, but **keep the original text and offsets** so quotes are verified against the raw file.
3. **Low-signal captures.**
   - D078 (SF Fair Chance URL) captured the generic SF Human Rights Commission page. Only one relevant line exists: "San Francisco's Fair Chance Ordinance protects residents with arrest or conviction history in affordable housing decisions."
   - D036 has about 10 relevant lines among about 200 menu lines.
   - The loader computes a signal score (share of lines longer than 60 characters that contain legal or housing vocabulary). It flags documents below 0.15 as `low_signal`, shown in the UI as "Partial capture".
4. **Versioned statute text inside one file.** Massachusetts General Laws pages carry markers such as `[ Introductory paragraph of clause (b) of subsection (1) effective until August 1, 2025. For text effective August 1, 2025, see below.]` (D052 §15B, D057 §87DDD½). The parser splits a document into version segments with validity intervals. Extraction reads the segment in force on the query date. Quotes must come from that segment.
5. **California history notes.** CA code pages end with notes like `(Amended by Stats. 2025, Ch. 340, Sec. 1. (AB 414) Effective January 1, 2026.)` and `Repealed as of January 1, 2030, by its own provisions.` (D023, D024). These are deterministic sources for `effective_date` and `sunset_date`.
6. **Relative effective-date clauses.** The model extracts the expression and anchor date; code computes the date (PLAN.md §11.7):
   - D069 FAIR Act: "first day of the twelfth month next following the date of enactment" + "approved July 20, 2026" → **2027-07-01**.
   - D066 NJ fee cap: "first day of the fourth month next following the date of enactment" + "Approved January 20, 2026" → **2026-05-01**.
   - D065 NJ Fair Chance: "first day of the seventh month next following the date of enactment" + "Approved June 18, 2021" → **2022-01-01**.
   - D076 San Diego algorithmic: "take effect and be in force on the thirtieth day from and after its final passage". The passage date is blank in the draft, so the date is unresolved from text.
7. **California chaptered bill with no effective-date sentence.** D022 AB 325 shows "CHAPTER 338 … Approved by Governor October 06, 2025".
   - The legal-calendar rule: a regular-session statute without an urgency clause takes effect January 1 of the following year.
   - This gives **2026-01-01**, corroborated by four CA history notes in the corpus (Stats. 2025 chapters → "Effective January 1, 2026"; Stats. 2023 → "Effective January 1, 2024").
   - Recorded with `derivation: "ca_regular_session_default"` and confidence 0.85.

---

## 4. Document-by-document map (54 text documents)

Abbreviations: **R** = rule candidate. **T-A** = official law text. **T-B** = official agency or guidance page describing law. **N** = no rule (context only).

### California (state)
| Doc | What it is | Tier | Rule candidates and key facts |
|---|---|---|---|
| D016 | CA Civil Rights Dept housing page | T-B | Source-of-income protection (Section 8); limits on using criminal history (arrests without conviction, sealed records). Supports screening_restrictions |
| D022 | AB 325 bill text (Ch. 338, approved 2025-10-06): adds B&P §16729, §16756.1 | T-A | **R algorithmic_rent_setting**: unlawful to use or distribute a "common pricing algorithm" as part of a conspiracy, or with coercion. Effective 2026-01-01 (calendar rule). SB 763 (penalties) is not in the corpus. Answer-key id in T1: `CA-ALG-01` |
| D023 | Civ. Code §1946.2 (Tenant Protection Act, just cause) | T-A | **R just_cause_eviction**. Applies after 12 months of occupancy. (e)(7) exempts housing with a certificate of occupancy within the previous 15 years. (i) local just-cause ordinances govern, and (i)(2) says a property is not subject to both. Amended by AB 1529, effective 2026-01-01; repealed 2030-01-01 |
| D024 | Civ. Code §1947.12 (AB 1482 rent cap) | T-A | **R rent_increase_limits**: 5% + CPI or 10%, whichever is lower. (d)(1) affordable/deed-restricted exempt; (d)(3) housing under stricter local rent control exempt (**precedence**); (d)(4) certificate of occupancy within 15 years exempt; (d)(5) separately alienable units with a qualifying owner and notice exempt. Operative 2024-04-01 version; repealed 2030-01-01 |
| D025 | Civ. Code §1950.5 (deposits) | T-A | **R security_deposits**: (c)(1) maximum one month's rent. (c)(5) small-landlord exception allows two months only if the landlord is a natural person and owns ≤2 properties with ≤4 units in total, so **a 5+ unit building cannot qualify**. (c)(6) the cap does not apply to deposits collected before 2024-07-01. Amended by AB 414, effective 2026-01-01 |
| D026 | Civ. Code §1950.6 (application screening fee) | T-A | **R application_screening_fees**: maximum $30, adjusted by CPI; no fee when no unit is available; receipt; refund of unused portion. Amended by AB 1170, effective 2026-01-01 |
| D027 | Gov. Code §12955 (FEHA) | T-A | **R screening_restrictions**: source-of-income discrimination prohibited. (o) with a government rent subsidy, the applicant must be offered alternative evidence instead of credit history (SB 267, effective 2024-01-01) |

### Los Angeles
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D039 | City Council motion 24-1031 (2024-09-03) asking LAHD to *report* on a possible algorithm ban | N | **Trap: a motion is not law.** Produces a no-rule finding for LA algorithmic_rent_setting |
| D040 | LAHD Just Cause Ordinance (JCO) page | T-B | **R just_cause_eviction**: covers most residential property *not* under the RSO, including buildings newer than 1978-10-01. Applies after 6 months of tenancy or lease expiry |
| D041 | LAHD RSO overview | T-B | **R rent_increase_limits** (RSO): applies to rental properties "first built on or before October 1, 1978". Changes effective 2026-02-02 (no utility add-on). The RSO also covers legal reasons for eviction (**R just_cause_eviction** for RSO units) and interest payments on security deposits (**R security_deposits**, interest, medium confidence) |
| D042 | RSO rent increase calculator | T-B | Key value **3%, valid 2025-07-01 to 2026-06-30**. Stale at the 2026-10-01 query date: the current figure is not in the corpus |
| D043 | Relocation assistance bulletins (rates effective 2026-07-01 to 2027-06-30) | T-B | Supports RSO/JCO no-fault relocation assistance (just_cause detail) |

### San Francisco
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D078 | SF HRC page (low-signal capture) | T-B | One line: the Fair Chance Ordinance protects people with arrest/conviction history **in affordable housing**. **R screening_restrictions**, coverage = affordable housing only, which is unknown for our addresses |
| D079 | Rent Board "Overview of Just Cause Evictions" | T-B | **R just_cause_eviction**: Admin. Code §37.9(a), 17 just causes. States that units with a certificate of occupancy **after June 13, 1979** are exempt from rent-increase limits but still subject to just cause, which gives the **rent_increase_limits coverage cutoff (CO on or before 1979-06-13)** |
| D080 | Annual increase announcement | T-B | Key value **1.6% for 2026-03-01 to 2027-02-28** (rent_increase_limits, ch. 37) |
| D081 | §37.10C news (algorithmic devices) | T-B | **R algorithmic_rent_setting**: went into effect **2024-10-14** |
| D082 | Relocation rates archive | T-B | Supports just_cause relocation amounts |
| D083 | Current rates | T-B | 1.6% allowable increase; **security deposit interest 4.2%** (2026-03-01 to 2027-02-28). **R security_deposits** (interest), medium confidence |

### San Diego
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D073 | SDMC ch. 9, art. 8, div. 7 Residential Tenant Protections (§§98.0701–98.0710), effective 2023-06-24, amended 2024-03-28 | T-A | **R just_cause_eviction**: §98.0704 requires just cause from the start of tenancy. §98.0703(k) exempts housing with a certificate of occupancy within the previous 15 years. San Diego has **no year built**, so the result is **unknown** for all 50. §98.0703(d) affordable-subsidy exemption explicitly excludes Section 8 |
| D076 | Staff report + draft ordinance O-2025-107 adding §§98.1101–98.1104 | T-A (draft) | **R algorithmic_rent_setting**: §98.1103 bans selling or using an "algorithmic device" to set rents; $1,000 per violation. Effective "30th day from final passage" with the passage date blank. Corroborated as codified by the link-only D074 URL ("98.1103-use-and-sale-of-algorithmic-devices-prohibited"). Status in_force, confidence medium; the brief dates it Jun 2025 |

### Berkeley
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D001 | Ordinance 7,992-N.S. amending BMC ch. 13.63 (passed to print 2025-11-18; file dated 2025-12-02) | T-A | **R algorithmic_rent_setting**: coordinated pricing algorithms banned; civil penalties up to $1,000. **No effective date in the supplied text** (see §8, open question 1) |
| D003 | Fair Chance Access to Housing Ordinance (BMC 13.106) | T-B | **R screening_restrictions**: no criminal-history inquiries. Exempts owner-occupied 1–3 unit properties, which a 5+ unit building cannot be |
| D004 | 2026 relocation assistance adjustments (effective 2026-01-01: $19,413 / $6,471) | T-B | Supports just_cause relocation |
| D005 | Tenant screening and application fees | T-B | **R application_screening_fees**: BMC 13.78.010 fee-rights statement; 13.78.016 no non-refundable fees for existing tenancies; publishes **$68.96 maximum for 2026** under state law |
| D006 | Measure BB changes (Nov 2024 ballot) | T-B | Coverage: multifamily **built before 1980** fully covered; new construction partially covered (just cause yes, rent ceiling no). The Annual General Adjustment is capped at 5% |
| D007 | Security deposits page | T-B | AB 12 summary; **R security_deposits** (interest for fully or partially covered units), medium confidence |
| D008 | 2026 Annual General Adjustment notice | T-B | Key value **1.0%** from 2026-01-01 (65% of CPI) |
| D009 | Coverage by unit type table | T-B | Fully covered: multifamily built before 1980. Partially covered: certificate of occupancy after June 1980. Just cause applies to both, so just cause **applies** to every multifamily address even without year built; rent ceiling is **unknown** |

### Santa Ana (laws only, no addresses)
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D084 | Rent Stabilization page | T-B | **R rent_increase_limits**: lower of 3% or 80% of CPI; **2.87% for 2026-09-01 to 2027-08-31**. **R just_cause_eviction** (reasons, relocation) |
| D085 | Adoption news | T-B | Both ordinances effective **2021-11-19**. Rent cap excludes buildings constructed after 1995-02-01. Just cause applies after 30 days and excludes housing produced in the last 15 years |

### New Jersey (state)
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D065 | P.L.2021, c.110 Fair Chance in Housing Act (approved 2021-06-18) | T-A | **R screening_restrictions**: no criminal-record inquiries before a conditional offer. Exempts owner-occupied premises of ≤4 units. Effective **2022-01-01** (seventh month rule) |
| D066 | P.L.2025, c.405 (C.46:8-18.1), approved 2026-01-20 | T-A | **R application_screening_fees**: maximum **$50**, CPI-adjusted from January 1 of the following year; exempts one- and two-family dwellings; penalties $500/$750/$1,000. Effective **2026-05-01** |
| D067 | DCA *Truth in Renting* guide (161 KB) | T-B | **R security_deposits**: N.J.S.A. 46:8-21.2, maximum 1.5 months' rent. **R just_cause_eviction**: Anti-Eviction Act N.J.S.A. 2A:18-61.1 (good cause; exempts owner-occupied 2–3 family). Rent control is municipal; **new multiple dwellings are exempt from local rent control for 30 years after completion** (behind the template's "new-construction exemption filing" example). Unconscionable-increase standard (rent_increase_limits candidate, low confidence) |
| D068 | DCR "Know your rights: housing" | T-B | **R screening_restrictions**: source of lawful income or rent (Section 8) under the Law Against Discrimination |
| D069 | P.L.2026, c.43 **FAIR Act** (approved 2026-07-20) | T-A | **R algorithmic_rent_setting**: coordinator/coordinating-function ban. **Effective 2027-07-01**, so `not_yet_effective` on 2026-10-01. §6.b "A municipality shall be prohibited from enacting an ordinance that conflicts with this act" is the **conflict evidence for T3**. Answer-key id `NJ-ALG-01` |

### Jersey City, Hoboken, Newark
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D036 | Jersey City Landlord/Tenant Relations page (mostly navigation) | T-B, low-signal | **R rent_increase_limits**: Rent Control Ordinance, ch. 260; "All 1-4 Unit Properties are exempt from rent control". Coverage also depends on the 30-year new-construction exemption (D067) |
| — | No supplied text for Jersey City's algorithmic ban (§218-12), Hoboken's (ch. 158, Art. II), Hoboken or Newark rent control (ecode360 D032–D034, D070–D072) | — | Tier C handling, §7 |

### Massachusetts (state)
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D045 | H.5222 status page ("An Act relative to preventing algorithmic rent fixing…"), referred to House Ways and Means 2026-03-12 | T-B | **R pending** algorithmic_rent_setting (`MA-ALG-P2`) |
| D046, D047 | S.2983 page + history ("An Act prohibiting algorithmic rent setting"), referred to Senate Ways and Means 2026-03-12 | T-B | **R pending** algorithmic_rent_setting (`MA-ALG-P1`) |
| D048 | G.L. c.40P §4 | T-A | "No city or town may enact, maintain or enforce rent control of any kind…" (with a narrow, voluntary-compliance exception). **R rent_increase_limits** (state bar). Drives the Boston and Cambridge **no-rule findings** |
| D049 | G.L. c.151B §4 | T-A | **R screening_restrictions**: clause 10, public assistance and housing subsidy (rental vouchers) |
| D050 | c.186 §11 | T-A | Notice to quit (14 days for nonpayment, written lease): just_cause_eviction (notice), medium |
| D051 | c.186 §12 | T-A | Tenancy-at-will termination notice: just_cause_eviction (notice), medium |
| D052 | c.186 §15B (versioned; Aug 1, 2025 version) | T-A | **R security_deposits**: deposit ≤ first month's rent. **R application_screening_fees**: upfront charges limited to first month, last month, security deposit and lock/key cost |
| D053 | c.186 §18 | T-A | Reprisal presumption: just_cause_eviction context, low |
| D057 | c.112 §87DDD½ (versioned; effective 2025-08-01) | T-A | **R application_screening_fees**: broker fee paid only by the party who engaged the broker |
| D058 | c.186 §31 | T-A | Notice to quit for nonpayment must include a rights form: just_cause_eviction (notice), medium |
| D011 | H.3744 (193rd session): Boston rent stabilization home-rule petition | T-B | Accompanied a study order on 2024-09-09, so it did not become law. **R status `failed`** (jurisdiction Boston, MA) |

### Boston, Cambridge
| Doc | What it is | Tier | Notes |
|---|---|---|---|
| D010 | Boston Fair Chance Tenant Selection Policy (Feb 2017, DND) | T-B | Applies only to providers receiving DND funding or with inclusionary units. **R screening_restrictions**, coverage unknown |
| D012 | Boston Fair Housing Commission page | T-B | **R screening_restrictions**: rental assistance (Section 8) is a protected class |
| D013, D014 | Housing Stability Notification Act (CBC 10-11.7) + tenant FAQ | T-B | **R just_cause_eviction** (notice): landlords must deliver a Notice of Tenants' Rights and Resources with any notice to quit; $300/day fines |
| D029 | Cambridge Human Rights Commission | T-B | **R screening_restrictions**: Fair Housing Ordinance ch. 14.04; source of income including Section 8 |
| D031 | Cambridge Tenants Rights and Resources Notification Ordinance, ch. 8.71 | T-B | **R just_cause_eviction** (notice) at the start and end of tenancy; $300/day |

---

## 5. Link-only sources and what they still tell us

| Doc | URL signal | Use |
|---|---|---|
| D002, D037 | Morgan Lewis Aug 2026 alert on algorithmic pricing litigation | Berkeley/Jersey City context; README says this alert gives "January 2026" for Berkeley |
| D015, D017–D021 | Justia and other mirrors of CA statutes | Redundant with official T-A texts; never cite mirrors when official text exists |
| D028 | Cleary Gottlieb, "California's antitrust law amendments kick in…" | Corroborates the AB 325 effective date (signal only) |
| D030 | cambridgeday.com/?p=158097 | Unknown content; no signal |
| D032–D034 | ecode360 Hoboken (check-terms) | Hoboken code chapters; titles unknown unless a human records them (PLAN.md §9.6) |
| D035 | "jersey-city-council-approves-realpage-ban…" | **Signal**: Jersey City algorithmic ban enacted |
| D038 | amlegal LAMC (check-terms) | Official LA RSO code; not supplied |
| D044 | "city-of-la-security-deposit-interest-requirement" | **Signal**: LA deposit-interest rule |
| D054 | "can-massachusetts-landlords-charge-an-application-fee" | Corroborates the §15B upfront-charge limits |
| D055 | "tag/cella-v-attorney-general" | **Signal**: the SJC case behind the struck ballot question |
| D056 | mass.gov 803 CMR 5 (CORI housing), 403 Forbidden | **Gap**: official text exists but blocked capture; MA criminal-record screening rules are unknown |
| D059 | WBUR, "massachusetts-high-court-rent-control-ballot-question-struck" (2026-06-23) | **Signal**: ballot question IP 25-21 failed (`MA-RENT-P1`, T5) |
| D060 | Day Pitney, "new-jersey-enacts-fair-act…" | Corroborates the FAIR Act |
| D061–D064 | Justia NJ statutes (10:5-12 LAD, 2A:18-61.1, 46:8-21.2, 46:8-26) | Official cites exist; text reaches us through D067/D068 |
| D070–D072 | ecode360 Newark (check-terms) | Newark code chapters; titles unknown |
| D074 | gocodebook SD 98.1103 | **Signal**: codification of the SD algorithmic ban |
| D075 | gocodebook SD "division-8-prohibition-of-discrimination-based-on-a-tenant-s-source-of-income" | **Signal**: SD source-of-income ordinance (single signal) |
| D077 | LASSD tenant protection ordinance explainer | Corroborates D073 |
| D086, D087 | OCBJ and PublicCEO: Santa Ana bans AI rent-pricing software (Feb 2026) | **Signals**: Santa Ana algorithmic ban (NS-3090) |

---

## 6. Expected inventory: jurisdiction × category (the silver key)

Legend:
- **R** = expect at least one rule record from supplied text (T-A/T-B).
- **C** = Tier C rule (no supplied text; supported by supplied signals).
- **F** = expect a "no rule at this level" finding.
- **P** = pending bill. **X** = failed measure.
- Confidence in brackets: h = high, m = medium, l = low.

| Jurisdiction | rent_increase_limits | just_cause_eviction | security_deposits | application_screening_fees | screening_restrictions | algorithmic_rent_setting |
|---|---|---|---|---|---|---|
| CA (state) | R Civ. §1947.12 [h] | R Civ. §1946.2 [h] | R Civ. §1950.5 [h] | R Civ. §1950.6 [h] | R Gov. §12955 [h]; CRD criminal-history guidance [m] | R B&P §16729 (AB 325), eff. 2026-01-01 [h] |
| Los Angeles, CA | R RSO (built ≤ 1978-10-01) [h] | R RSO just cause [m] + R JCO [h] | R RSO deposit interest [m] | F [m] | F [m] | **F** (motion only, D039) [h] |
| San Francisco, CA | R Admin. Code ch. 37 (CO ≤ 1979-06-13) [h] | R §37.9 [h] | R deposit interest [m] | F [m] | R Fair Chance (affordable housing only) [m] | R §37.10C, eff. 2024-10-14 [h] |
| San Diego, CA | F (state cap only) [h] | R §98.0704 [h] | F [m] | F [m] | C source of income (D075) [l] | R §98.1103 [m] |
| Berkeley, CA | R Rent Ordinance / AGA [h] | R Rent Ordinance good cause [h] | R deposit interest [m] | R BMC 13.78 [h] | R BMC 13.106 [h] | R BMC 13.63 (date open question) [h] |
| Santa Ana, CA | R RSO (3% / 80% CPI) [h] | R JCO [h] | F [m] | F [m] | F [m] | C Ord. NS-3090 [m] |
| NJ (state) | F or R unconscionable standard [l] | R Anti-Eviction Act [h] | R 46:8-21.2 [h] | R C.46:8-18.1 $50, eff. 2026-05-01 [h] | R Fair Chance Act, eff. 2022-01-01 [h]; R LAD source of income [m] | R FAIR Act, eff. 2027-07-01 [h] |
| Jersey City, NJ | R ch. 260 rent control [h] | F [m] | F [m] | F [m] | F [m] | C §218-12 (`JC-ALG-01`) [h] |
| Hoboken, NJ | C rent control (only if a link title confirms it) [l] | F [m] | F [m] | F [m] | F [m] | C ch. 158 Art. II (`HOB-ALG-01`) [h] |
| Newark, NJ | C rent control (only if a link title confirms it) [l] | F [m] | F [m] | F [m] | F [m] | **F** (T2: "neither for Newark") [h] |
| MA (state) | R c.40P §4 bar [h]; X IP 25-21 ballot question (`MA-RENT-P1`) [h] | R c.186 §§11, 12, 31 notice rules [m] | R c.186 §15B [h] | R c.186 §15B upfront charges [h]; R c.112 §87DDD½ [h] | R c.151B §4(10) [h]; CORI blocked (D056) | P S.2983 (`MA-ALG-P1`) [h]; P H.5222 (`MA-ALG-P2`) [h] |
| Boston, MA | **F** (barred by c.40P) [h]; X H.3744 [m] | R HSNA notice [m] | F [m] | F [m] | R Fair Housing (rental assistance) [m]; R DND Fair Chance policy [l] | F [h] |
| Cambridge, MA | **F** (barred by c.40P) [h] | R ch. 8.71 notice [m] | F [m] | F [m] | R ch. 14.04 source of income [m] | F [h] |

Our count is about 55–62 rule records and 25–33 empty cells. The official key has 58 rules and 19 findings, so it reports findings only for the more salient empty cells. We still emit a finding for every empty cell with a reason; extra findings carry no stated penalty.

---

## 7. Evidence tiers (how Tenantly treats gaps honestly)

| Tier | Definition | `quoted_span` comes from | Confidence cap | How lookups use it |
|---|---|---|---|---|
| A | Official law text in the corpus | The corpus document, byte-verified | 1.0 | Normal |
| B | Official agency or guidance page in the corpus describing the law | The corpus document, byte-verified | 0.9 | Normal; the citation names the underlying law (e.g. "N.J.S.A. 46:8-21.2", sourced via D067) |
| C | Law exists per **≥2 independent supplied signals**, but no text was supplied | An exact span from a **supplementary** document (public brief, README, `change_tests.json`); never invented | 0.6 | `applies`/`unknown` per coverage, with an explanation that says the text was not supplied |
| C1 | Only **one** supplied signal | Same as C | 0.3 | Always `unknown` |

**Signals that count:**
1. The public challenge brief lists the measure with a citation.
2. A link-only manifest URL slug names it.
3. `change_tests.json` references it.
4. The README names it.
5. A human-recorded link title (`dataset_supplement/link_titles.csv`).

**Tier C records:**
- `source_doc_id` = the link-only manifest id where the law lives (e.g. D035).
- `source_url` = that URL.
- `quoted_span` = the exact supplementary text.
- `conflict_note` begins: "Source text not supplied (link-only). Quoted span is from <supplementary doc>, not the ordinance."

The UI shows a "Text not supplied" badge. This is the only honest way to score on T2 and on Jersey City/Hoboken coverage without inventing quotes.

---

## 8. Open questions and discrepancies Tenantly surfaces

| # | Item | What the supplied data shows | Tenantly behavior |
|---|---|---|---|
| 1 | Berkeley ch. 13.63 effective date | README: "March 1, 2026 in the ordinance text; January 2026 per an August 2026 law-firm alert". **D001 as supplied contains no effective date.** | `effective_date` "2026-03-01" with `conflict_note` listing both dates and noting the capture gap. Both dates precede 2026-10-01, so the status is unaffected. Open-question card in the UI |
| 2 | NJ FAIR Act vs Jersey City/Hoboken bans | D069 §6.b bars conflicting municipal ordinances | Conflict flag on JC/HOB addresses from 2027-07-01 (T3) |
| 3 | LA RSO formula effective date | README: 2026-02-02 (LAHD) vs 2026-01-24 (landlord association); D041 says "Effective February 2, 2026" | Date interval; surfaced only for queries between the two dates |
| 4 | CA screening-fee cap figure | D026: $30 CPI-adjusted, no official figure; D005 Berkeley publishes $68.96 for 2026 | `key_value` "$30 adjusted annually for CPI (no single official 2026 figure; Berkeley Rent Board publishes $68.96)" |
| 5 | LA RSO allowable increase at query date | D042: 3% only through 2026-06-30 | "The figure for this date is not in our sources" (stale key value) |
| 6 | San Diego algorithmic effective date | D076: "30th day from final passage", passage date blank | Status in_force, `effective_date` "2025" (year precision) with note; the brief says Jun 2025 |
| 7 | SF Fair Chance capture | D078 is a generic HRC page | "Partial capture" badge; coverage unknown |
| 8 | MA criminal-record screening (803 CMR 5) | D056 official page returned 403 | Shown as a known gap in the reasoning boundary |

---

## 9. Address data: facts, gaps, traps

### 9.1 Counts by legal city (postal names resolved)
Los Angeles 80, San Francisco 80, San Diego 50 (includes 1 "San Ysidro"), Berkeley 40, Jersey City 50, Hoboken 40, Newark 50, Boston 60, Cambridge 50.

**Boston rows carry neighborhood names as postal city:** Allston 3, Brighton 4, Dorchester 13, East Boston 6, Hyde Park 1, Jamaica Plain 1, Mattapan 1, Roxbury 7, South Boston 1, "Boston" 23.

State totals: **CA 250, NJ 140, MA 110.**

### 9.2 Missing values
| Field | Missing |
|---|---|
| year_built | 212 in total: San Diego 50, Berkeley 40, NJ 106 (Jersey City 22, Hoboken 36, Newark 48), Boston 8, LA 6, SF 2 |
| units | Berkeley 40, Boston 60, Jersey City 50, Newark 50, Hoboken 39 of 40, LA 3 |
| zip | Empty for SF (80) and Cambridge (50) |

### 9.3 Derived facts (intervals, recorded with provenance)
| Source dataset | use_code / description | Derived units interval | Other derived facts |
|---|---|---|---|
| LA County eGIS | 0500, 0501, 050V, 050C, 0551 "Five or more apartments" | [5, ∞) when units are missing | |
| DataSF | A5, FS5, F5 → [5, 14]; A15 → [15, ∞); TIC "4 units or less" → [1, 4] | | **A0398: units=5 but TIC ≤4 → record conflict** |
| SANDAG | land use 14–16 "(5+ units)" | units present | |
| Alameda (Berkeley) | 7200, 7700, 7800 "(5+ units)" | [5, ∞) | |
| Boston FY2026 | A/112 "APT 7-30 UNITS" → [7, 30]; other A/ classes → [7, ∞) (Boston "A" = apartment 7+; confidence medium) | | A/125 "SUBSD HOUSING S-8" → `subsidized=true` (26 rows); A/118 "ELDERLY HOME" → `property_type=elderly_home` (review) |
| Cambridge FY2026 | 111 "4-8-UNIT-APT", 112 ">8-UNIT-APT" | units present | |
| NJOGIS MOD-IV | Class **4C = apartment, 5+ units** → [5, ∞). The building description gives units via the `(\d+)U` token, summing "/" parts (e.g. "3B-7U/4B-24U-G" → 31; "2F-4U/2F-2U" → 6) | | "AFFORDABL" → `subsidized=true` (A0049); "CO-OP" → `cooperative=true` (A0125, A0136). **A0028 "3SF3UG" (3U) vs class 4C (≥5) → record conflict.** A0076 "3SB2UG" → conflict |

**Record conflicts** (empty interval intersection): the fact becomes **unknown**, `record_conflict=true`, and the UI explains both sources.

### 9.4 Geocoding traps
- **NJ ZIPs are mostly owner-mailing ZIPs.** 83 of 140 are inconsistent with the city: 11219 and 11211 (Brooklyn), 10003 (Manhattan), 78746 (Texas), 08805, and others. Valid sets: Hoboken {07030}; Jersey City {07302–07311}; Newark {07101–07199}. Inconsistent ZIPs are **dropped** before geocoding, with `zip_suspect=true`.
- **Street ranges:** "1031-1035 CLINTON ST", "322-322.5 Western Ave", "14.5-16 Vandine St" → geocode the first number (322, 14). Keep the original label.
- **Typos:** "NORFLOK ST" (Newark). Fallback cascade: Census one-line → Nominatim.
- **Mailing city is not legal city.** Boston neighborhoods, San Ysidro → San Diego, and LA neighborhood ZIPs (91601 North Hollywood, 91402 Panorama City, 91042 Tujunga, 91344 Granada Hills, …). Point-in-polygon decides.

### 9.5 Threshold edge counts (where "unknown" must appear)
| City | Rule | Applies | Unknown | Excluded / other |
|---|---|---|---|---|
| Los Angeles | RSO (CO ≤ 1978-10-01) | 47 built ≤1977 | 2 built 1978 + 6 missing | 25 built ≥1980 → JCO instead |
| San Francisco | Rent Ordinance (CO ≤ 1979-06-13) | 71 built ≤1977 | 2 missing (none built 1979) | 7 built ≥1980 |
| AB 1482 15-year exemption, CA addresses (as of 2026-10-01) | Threshold CO after 2011-10-01 | built ≤2010 not exempt | built 2011 (CA has none) | built ≥2012 exempt: LA 4, SF 1 |
| San Diego, Berkeley | Every year-built test | — | unknown | — |
| Jersey City | Rent control 30-year new-construction exemption | 28 built ≤1977 | 22 missing | — |
| Boston, Cambridge | Rent control | barred: **no rent cap ever** | — | — |

### 9.6 Change tests: exact expected behavior (from `dev/change_tests.json`)
Counts assume geocoding confirms the legal cities in §9.1.

| Test | Type | Rule ids (theirs) | Expected |
|---|---|---|---|
| T1 | `as_of` 2025-12-31 → 2026-01-02, states [CA] | CA-ALG-01 | Every CA address `not_yet_effective` → `applies`. **Affected: all 250 CA addresses** |
| T2 | `boundary` on 2026-10-01 | HOB-ALG-01, JC-ALG-01 | HOB only in Hoboken (40); JC only in Jersey City (50); neither in Newark. **Affected: 90** |
| T3 | `as_of` 2026-10-01 → 2027-07-02, states [NJ], conflict_with [JC-ALG-01, HOB-ALG-01] | NJ-ALG-01 | Every NJ address `not_yet_effective` → `applies`. **Affected: 140; conflict flags: 90 (Jersey City + Hoboken)** |
| T4 | `pending` on 2026-10-01, states [MA] | MA-ALG-P1, MA-ALG-P2 | `pending` for every Boston and Cambridge address. **Affected if enacted: all 110 MA addresses** |
| T5 | `negative` on 2026-10-01, states [MA] | MA-RENT-P1 | IP 25-21 recorded as `failed`; no rent cap anywhere in MA. **Affected: empty** |
