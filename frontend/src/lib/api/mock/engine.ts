// Illustrative mock data shaped like the real API. Not legal information.
import type {
  AddressSummary,
  AffectedAddress,
  BuildingFacts,
  CategoryBlock,
  ChangeEvent,
  Conflict,
  DecisiveQuestion,
  FactValue,
  Finding,
  IngestJob,
  IngestStage,
  JurisdictionStack,
  LookupResponse,
  OpenQuestion,
  ProofResponse,
  Result,
  RuleDetail,
  RuleResult,
  SourceDoc,
  TimelineResponse,
  UpcomingChange,
} from "../types";
import {
  ADDRESSES,
  CATEGORIES,
  CITIES,
  cityOf,
  COMPILED_AT,
  DATA_VERSION,
  DISCLAIMER,
  JURIS,
  PENDING_MA,
  RANGE,
  RULES,
  b,
  cite,
  hash,
  sha,
  stateOf,
  type Facts,
  type RuleDef,
  type SeedAddr,
} from "./data";

const DEFAULT_AS_OF = "2026-10-01";

export const OPEN_QUESTIONS: OpenQuestion[] = [
  {
    oq_id: "oq_ca_fee_figure",
    title: b("No single official 2026 dollar figure", "No hay una cifra oficial única para 2026"),
    detail: b(
      "The law sets $30 adjusted for inflation, but our sources do not include one official adjusted amount for 2026.",
      "La ley fija $30 ajustados por inflación, pero nuestras fuentes no incluyen un monto oficial ajustado para 2026.",
    ),
    rule_ids: ["ca_civ_1950_6"],
    sources: [cite("ca_civ_1950_6", "Cal. Civ. Code § 1950.6(b)", "in no case shall the fee exceed thirty dollars ($30), adjusted annually")],
    changes_answer_between: null,
  },
  {
    oq_id: "oq_hob_preemption",
    title: b("Does the FAIR Act override Hoboken's ban?", "¿La Ley FAIR reemplaza la prohibición de Hoboken?"),
    detail: b(
      "From July 1, 2027 both rules cover the same conduct. Our sources do not say which one controls.",
      "Desde el 1 de julio de 2027 ambas reglas cubren la misma conducta. Nuestras fuentes no dicen cuál prevalece.",
    ),
    rule_ids: ["hob_ch158", "nj_fair_act"],
    sources: [],
    changes_answer_between: ["2027-07-01", "2028-12-31"],
  },
];

const extraRules: RuleDef[] = [];
const extraBreakpoints: Record<string, { date: string; rule_ids: string[] }[]> = {};
const allRules = () => [...RULES, ...extraRules];

function addrById(id: string): SeedAddr | undefined {
  return ADDRESSES.find((a) => a.id === id);
}

export function addressSummary(a: SeedAddr): AddressSummary {
  return {
    address_id: a.id,
    label: a.label,
    street: a.street,
    postal_city: a.postal,
    zip: a.zip,
    state: stateOf(a),
    lat: a.lat,
    lon: a.lon,
    legal_city: a.legal,
    is_sample: true,
  };
}

export function jurisdictionStack(a: SeedAddr): JurisdictionStack {
  const info = cityOf(a.legal);
  const mismatch = a.postal !== a.legal;
  return {
    state: info.state,
    county: info.county,
    city: info.city,
    mailing_city: a.postal,
    mailing_mismatch: mismatch,
    note: mismatch
      ? b(
          `Mailed as ${a.postal}. Legally inside the City of ${a.legal}.`,
          `Se envía correo como ${a.postal}. Legalmente dentro de la Ciudad de ${a.legal}.`,
        )
      : null,
    resolution: { method: "point_in_polygon", geocoder: "census_batch", census_agrees: true },
  };
}

function fv(
  value: FactValue["value"],
  source: FactValue["source"],
  en: string,
  es: string,
  basis: string | null = null,
): FactValue {
  return { value, interval: null, source, basis, record_conflict: false, label: b(en, es) };
}

function buildingFacts(a: SeedAddr, f: Facts, user: boolean): BuildingFacts {
  const yb = f.year_built;
  return {
    year_built:
      yb == null
        ? fv(null, "missing", "Year built not in public records", "Año de construcción no está en registros públicos")
        : fv(yb, user && a.facts.year_built == null ? "user" : "assessor", `Built ${yb}`, `Construido en ${yb}`),
    units: a.assessor_derived_units
      ? fv(f.units, "assessor_derived", `${f.units} units`, `${f.units} unidades`, a.assessor_derived_units)
      : fv(f.units, "assessor", `${f.units} units`, `${f.units} unidades`),
    property_type: fv("multifamily", "assessor", "Multifamily residential", "Residencial multifamiliar"),
    subsidized:
      f.subsidized == null
        ? fv(null, "missing", "Subsidy status not public", "Estado de subsidio no es público")
        : fv(f.subsidized, "derived", f.subsidized ? "Subsidized" : "Not flagged as subsidized", f.subsidized ? "Subsidiado" : "No marcado como subsidiado"),
    use_code: "R4",
    use_description: "Apartment building",
    source_dataset: `${stateOf(a)} county assessor roll, 2026`,
    zip_suspect: a.id === "A0003",
  };
}

function rulesFor(a: SeedAddr): RuleDef[] {
  const info = cityOf(a.legal);
  return allRules().filter((r) => r.jur.id === info.state.id || r.jur.id === info.city.id);
}

function kvFor(def: RuleDef, asOf: string) {
  return (def.key_values ?? []).filter(
    (k) => (k.valid_from == null || k.valid_from <= asOf) && (k.valid_to == null || k.valid_to >= asOf),
  );
}

function evaluate(def: RuleDef, f: Facts, asOf: string): RuleResult | null {
  const out = def.coverage_test ? def.coverage_test(f, asOf) : { covered: true, conditions: [], missing: [] };
  if (out.covered === false) return null;
  let result: Result = out.covered === null ? "unknown" : "applies";
  if (def.eff && def.eff > asOf) result = "not_yet_effective";
  const conflicts: Conflict[] = [];
  if (def.conflict && asOf >= def.conflict.active_from) {
    conflicts.push({
      with_rule_id: def.conflict.with_rule_id,
      kind: "possible_preemption",
      explanation: def.conflict.explanation,
      evidence: null,
      active_from: def.conflict.active_from,
    });
  }
  const missingLabel = out.missing.map((m) => m.replace(/_/g, " ")).join(", ");
  const reason =
    result === "unknown"
      ? b(`We are missing: ${missingLabel}.`, `Nos falta: ${missingLabel}.`)
      : result === "not_yet_effective"
        ? b(`Takes effect ${def.eff}.`, `Entra en vigor el ${def.eff}.`)
        : b(
            "The building meets every condition for this rule on the selected date.",
            "El edificio cumple todas las condiciones de esta regla en la fecha seleccionada.",
          );
  return {
    rule_id: def.id,
    category: def.category,
    title: def.title,
    jurisdiction: def.jur,
    result,
    rule_status: def.eff && def.eff > asOf ? "not_yet_effective" : def.status === "not_yet_effective" ? "in_force" : def.status,
    effective_date: def.eff,
    effective_note: null,
    summary: def.summary,
    who: def.who,
    reason,
    key_values: kvFor(def, asOf),
    conditions: out.conditions,
    caveats: def.caveats ?? [],
    missing_facts: out.missing,
    superseded_by: null,
    governs_over: def.governs_over ?? [],
    conflicts,
    conflict_flag: conflicts.length > 0,
    citation: def.citation,
    extra_citations: [],
    confidence: def.confidence ?? 0.93,
    review_flag: def.review_flag ?? false,
    open_question_ids: def.open_question_ids ?? [],
    audio: { en: null, es: null },
  };
}

function findingsFor(a: SeedAddr): Finding[] {
  const info = cityOf(a.legal);
  const out: Finding[] = [];
  if (info.state.id === "ma") {
    out.push({
      finding_id: `f_${info.city.id}_rent`,
      category: "rent_increase_limits",
      jurisdiction: info.city,
      reason_code: "barred_by_state",
      explanation: b(
        "Massachusetts law bars cities from adopting rent control.",
        "La ley de Massachusetts prohíbe a las ciudades adoptar control de rentas.",
      ),
      evidence: [cite("ma_40p_4", "M.G.L. c. 40P § 4", "No city or town shall enact, maintain or enforce any ordinance or by-law which provides for rent control.")],
    });
  }
  if (info.city.id === JURIS.la.id) {
    out.push({
      finding_id: "f_la_algo",
      category: "algorithmic_rent_setting",
      jurisdiction: info.city,
      reason_code: "motion_only",
      explanation: b("A 2024 council motion asked for a report. It is not law.", "Una moción del concejo de 2024 pidió un informe. No es ley."),
      evidence: [cite("la_cf_24_1183", "L.A. Council File 24-1183", "Instruct the Housing Department to report back on the use of algorithmic rent-setting software.", { tier: "B" })],
    });
  }
  if (info.city.id === JURIS.nwk.id) {
    out.push({
      finding_id: "f_nwk_algo",
      category: "algorithmic_rent_setting",
      jurisdiction: info.city,
      reason_code: "none_in_sources",
      explanation: b("Our sources contain no Newark rule on rent-setting software.", "Nuestras fuentes no contienen una regla de Newark sobre software para fijar rentas."),
      evidence: [],
    });
  }
  return out;
}

const HEADLINES: Record<Result, (t: string) => [string, string]> = {
  applies: (t) => [`${t} applies.`, `${t} aplica.`],
  unknown: (t) => [`Can't tell yet whether ${t} applies.`, `Aún no se sabe si ${t} aplica.`],
  superseded: (t) => [`${t} is overridden here.`, `${t} está reemplazada aquí.`],
  not_yet_effective: (t) => [`${t} is not in effect yet.`, `${t} aún no entra en vigor.`],
  pending: (t) => [`${t} is proposed, not law.`, `${t} es una propuesta, no ley.`],
};
const ORDER: Result[] = ["applies", "unknown", "not_yet_effective", "superseded", "pending"];

export function buildLookup(addressId: string, asOf: string, override?: Partial<Facts>): LookupResponse | null {
  const a = addrById(addressId);
  if (!a) return null;
  const facts: Facts = { ...a.facts, ...(override ?? {}) };
  const user = override != null && Object.keys(override).length > 0;
  const results = rulesFor(a)
    .map((d) => evaluate(d, facts, asOf))
    .filter((r): r is RuleResult => r != null);

  // supersession
  for (const gov of results) {
    if (gov.result !== "applies") continue;
    for (const target of results) {
      if (gov.governs_over.includes(target.rule_id) && target.result === "applies") {
        const def = allRules().find((d) => d.id === target.rule_id);
        target.result = "superseded";
        target.superseded_by = gov.rule_id;
        target.reason = def?.supersede_reason ?? b("Overridden by a local rule here.", "Reemplazada por una regla local aquí.");
      }
    }
  }

  const findings = findingsFor(a);
  const categories: CategoryBlock[] = CATEGORIES.map((c) => {
    const rs = results
      .filter((r) => r.category === c.key)
      .sort((x, y) => ORDER.indexOf(x.result) - ORDER.indexOf(y.result));
    let fs = findings.filter((f) => f.category === c.key);
    if (rs.length === 0 && fs.length === 0) {
      fs = [
        {
          finding_id: `f_${a.id}_${c.key}_none`,
          category: c.key,
          jurisdiction: cityOf(a.legal).state,
          reason_code: "none_in_sources",
          explanation: b("Our sources contain no rule on this for this address.", "Nuestras fuentes no contienen una regla sobre esto para esta dirección."),
          evidence: [],
        },
      ];
    }
    const top = rs[0];
    const [en, es] = top
      ? HEADLINES[top.result](top.title.split(" (")[0] ?? top.title)
      : [fs[0]!.explanation.en, fs[0]!.explanation.es];
    return { category: c.key, label: c.label, headline: b(en, es), results: rs, findings: fs };
  });

  const isMA = cityOf(a.legal).state.id === "ma";
  const pending: RuleResult[] = isMA
    ? PENDING_MA.map((p) => ({
        rule_id: p.id,
        category: "algorithmic_rent_setting",
        title: p.title,
        jurisdiction: JURIS.MA,
        result: "pending",
        rule_status: "pending",
        effective_date: null,
        effective_note: null,
        summary: p.summary,
        who: b("Residential rentals in Massachusetts, if passed.", "Alquileres residenciales en Massachusetts, si se aprueba."),
        reason: b("Proposed in the Legislature. Not law.", "Propuesto en la Legislatura. No es ley."),
        key_values: [],
        conditions: [],
        caveats: [],
        missing_facts: [],
        superseded_by: null,
        governs_over: [],
        conflicts: [],
        conflict_flag: false,
        citation: p.citation,
        extra_citations: [],
        confidence: 0.9,
        review_flag: false,
        open_question_ids: [],
        audio: { en: null, es: null },
      }))
    : [];
  const failed = isMA
    ? [
        {
          rule_id: "ma_ip_25_21",
          title: "Rent-control ballot question (IP 25-21)",
          note: b("Struck before the vote. Not law.", "Anulada antes de la votación. No es ley."),
          citation: cite("ma_ip_25_21", "Initiative Petition 25-21", "An Act enabling local rent stabilization.", { tier: "B" }),
        },
      ]
    : [];

  const upcoming: UpcomingChange[] = results
    .filter((r) => r.result === "not_yet_effective" && r.effective_date && r.effective_date <= RANGE.end)
    .map((r) => ({
      date: r.effective_date as string,
      rule_id: r.rule_id,
      title: r.title,
      from: "none" as const,
      to: "applies" as const,
      summary: r.summary,
    }));

  const counts: Record<Result, number> = { applies: 0, unknown: 0, superseded: 0, not_yet_effective: 0, pending: pending.length };
  results.forEach((r) => (counts[r.result] += 1));

  const open_questions = OPEN_QUESTIONS.filter((q) => q.rule_ids.some((id) => results.some((r) => r.rule_id === id)));

  let decisive_question: DecisiveQuestion | null = null;
  const needYear = results.filter((r) => r.missing_facts.includes("year_built"));
  const needSub = results.filter((r) => r.missing_facts.includes("subsidized_or_affordable"));
  if (needYear.length) {
    decisive_question = {
      fact: "year_built",
      prompt: b("What year was the building built?", "¿En qué año se construyó el edificio?"),
      input: "year",
      resolves_rule_ids: needYear.map((r) => r.rule_id),
    };
  } else if (needSub.length) {
    decisive_question = {
      fact: "subsidized_or_affordable",
      prompt: b("Is the unit subsidized or affordable housing?", "¿La unidad es vivienda subsidiada o asequible?"),
      input: "boolean",
      resolves_rule_ids: needSub.map((r) => r.rule_id),
    };
  }

  return {
    address: addressSummary(a),
    jurisdiction: jurisdictionStack(a),
    facts: buildingFacts(a, facts, user),
    as_of: asOf,
    categories,
    pending,
    failed,
    upcoming,
    counts,
    decisive_question,
    open_questions,
    reasoning_boundary: {
      checked: [
        b("Legal city from map boundaries", "Ciudad legal según límites del mapa"),
        b("Year built and unit count from public records", "Año de construcción y unidades según registros públicos"),
        b("Effective dates on the selected date", "Fechas de vigencia en la fecha seleccionada"),
      ],
      not_checked: [
        b("Owner type (not public)", "Tipo de propietario (no es público)"),
        b("Subsidy status unless public records flag it", "Estado de subsidio salvo que los registros lo indiquen"),
      ],
      assumptions: [b("Year built stands in for the certificate-of-occupancy date", "El año de construcción sustituye la fecha del certificado de ocupación")],
    },
    facts_source: user ? "user" : "data",
    sources_retrieved_at: "2026-10-01",
    is_projection: asOf > DEFAULT_AS_OF,
    data_version: DATA_VERSION,
    disclaimer: DISCLAIMER,
    fallback: false,
  };
}

function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

export function buildTimeline(addressId: string): TimelineResponse | null {
  const a = addrById(addressId);
  if (!a) return null;
  const defs = rulesFor(a);
  const points = new Map<string, string[]>();
  points.set(RANGE.start, []);
  for (const d of defs) {
    if (d.eff && d.eff > RANGE.start && d.eff <= RANGE.end) points.set(d.eff, [...(points.get(d.eff) ?? []), d.id]);
    for (const k of d.key_values ?? []) {
      if (k.valid_from && k.valid_from > RANGE.start && k.valid_from <= RANGE.end && !points.has(k.valid_from)) points.set(k.valid_from, []);
    }
  }
  for (const e of extraBreakpoints[addressId] ?? []) points.set(e.date, [...(points.get(e.date) ?? []), ...e.rule_ids]);
  const dates = [...points.keys()].sort();
  const breakpoints = dates.map((date) => {
    const ids = points.get(date) ?? [];
    const label =
      date === RANGE.start
        ? b("Start of range", "Inicio del rango")
        : ids.length === 0
          ? b("New published figure takes effect", "Entra en vigor una nueva cifra publicada")
          : b(`${ids.map((id) => defs.find((d) => d.id === id)?.title.split(" (")[0] ?? id).join(", ")} takes effect`, `Entra en vigor: ${ids.join(", ")}`);
    return { date, label, rule_ids: ids };
  });
  const segments = dates.map((start, i) => ({
    start,
    end: i < dates.length - 1 ? dayBefore(dates[i + 1]!) : null,
    lookup: buildLookup(addressId, start) as LookupResponse,
  }));
  return { address_id: addressId, range: RANGE, breakpoints, segments, data_version: DATA_VERSION };
}

// ---------- geography ----------
export function jurisdictionGeo(id: string) {
  const entry = Object.values(CITIES).find((c) => c.city.id === id);
  if (!entry) return null;
  const [lat, lon] = entry.center;
  const n = 7 + (hash(id) % 3);
  const coords: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const ang = (i / n) * Math.PI * 2;
    const r = 0.022 + ((hash(`${id}${i}`) % 100) / 100) * 0.014;
    coords.push([lon + (r * Math.cos(ang)) / Math.cos((lat * Math.PI) / 180), lat + r * Math.sin(ang)]);
  }
  coords.push(coords[0]!);
  return {
    type: "Feature" as const,
    properties: { id, name: entry.city.name, label: entry.city.label },
    geometry: { type: "Polygon" as const, coordinates: [coords] },
  };
}

// ---------- rules ----------
export function ruleDetail(def: RuleDef): RuleDetail {
  const counts: Record<Result, number> = { applies: 0, unknown: 0, superseded: 0, not_yet_effective: 0, pending: 0 };
  for (const a of ADDRESSES) {
    const l = buildLookup(a.id, DEFAULT_AS_OF);
    const r = l?.categories.flatMap((c) => c.results).find((x) => x.rule_id === def.id);
    if (r) counts[r.result] += 1;
  }
  return {
    rule_id: def.id,
    category: def.category,
    title: def.title,
    jurisdiction: def.jur,
    rule_status: def.status,
    effective_date: def.eff,
    effective_note: null,
    requirement: def.requirement,
    summary: def.summary,
    who: def.who,
    coverage_text: def.coverage,
    exemptions: [],
    key_values: def.key_values ?? [],
    penalty: def.penalty ?? null,
    citation: def.citation,
    extra_citations: [],
    relations: (def.governs_over ?? []).map((other) => ({
      type: "governs_over",
      other_rule_id: other,
      explanation: def.supersede_reason ?? b("This local rule controls over the state rule where both cover a building.", "Esta regla local prevalece sobre la estatal cuando ambas cubren un edificio."),
      evidence: def.citation,
      active_from: def.eff,
    })),
    confidence: def.confidence ?? 0.93,
    review_flag: def.review_flag ?? false,
    open_question_ids: def.open_question_ids ?? [],
    provenance: {
      models: ["extractor-a", "extractor-b"],
      prompt_versions: { extract: "v7", verify: "v3" },
      votes: { applies_scope: "2/2" },
      adjudicated_fields: def.review_flag ? ["citation.quote"] : [],
      audit_ids: [`aud_${def.id}`],
    },
    counts_at_default_date: counts,
  };
}

export function listRuleDefs() {
  return allRules();
}

export function allFindings(): Finding[] {
  const seen = new Map<string, Finding>();
  for (const a of ADDRESSES) for (const f of findingsFor(a)) seen.set(f.finding_id, f);
  return [...seen.values()];
}

export function sourceDoc(docId: string, ruleId: string | null): SourceDoc | null {
  const def = allRules().find((r) => r.citation.doc_id === docId && (!ruleId || r.id === ruleId)) ?? allRules().find((r) => r.citation.doc_id === docId);
  if (!def) return null;
  const before = `${def.citation.cite.split("(")[0]!.trim()}. `;
  const lead = "Except as otherwise provided in this section, ";
  const after = " The provisions of this section shall be construed liberally to protect tenants.";
  const text = `${before}${lead}${def.citation.quote}${after}`;
  const start = before.length + lead.length;
  return {
    doc_id: docId,
    title: def.title,
    url: def.citation.url,
    retrieved_at: def.citation.retrieved_at,
    doc_sha256: def.citation.doc_sha256,
    sha_ok: def.citation.tier === "C" ? null : true,
    jurisdiction_label: def.jur.label,
    doc_type: def.jur.level === "state" ? "statute" : "ordinance",
    low_signal: def.citation.low_signal,
    versions: [{ label: "Current", valid_from: def.eff, valid_to: null, in_force_on_default: true }],
    window: { text, start: 0, end: text.length, highlights: [{ start, end: start + def.citation.quote.length, rule_id: def.id }] },
    total_chars: 4000 + (hash(docId) % 20000),
  };
}

// ---------- changes ----------
function affectedFrom(ids: string[], rule: string, before: Result | "none", after: Result | "none", conflict = false): AffectedAddress[] {
  return ids
    .map((id) => addrById(id))
    .filter((a): a is SeedAddr => !!a)
    .map((a) => ({
      address_id: a.id,
      label: a.label,
      lat: a.lat,
      lon: a.lon,
      legal_city: a.legal,
      before: [{ rule_id: rule, result: before }],
      after: [{ rule_id: rule, result: after }],
      conflict_flag: conflict,
    }));
}
const idsIn = (cities: string[], max: number) => ADDRESSES.filter((a) => cities.includes(a.legal)).slice(0, max).map((a) => a.id);
const passed = { passed: true, detail: "Matches the test definition" };

export const CHANGES: ChangeEvent[] = [
  {
    change_id: "chg_t1", kind: "test", test_id: "T1", title: "AB 325 takes effect", test_type: "as_of",
    summary: b("California's ban on shared pricing algorithms starts covering rentals statewide.", "La prohibición de California sobre algoritmos de precios compartidos empieza a cubrir alquileres en todo el estado."),
    created_at: "2026-10-01T23:00:00Z", rule_ids: ["ca_ab325"], compare: { before: "2025-12-31", after: "2026-01-01" },
    affected_count: 250, conflict_count: 0, expected_check: passed,
    affected: affectedFrom(idsIn(["San Francisco", "Los Angeles", "San Diego", "Oakland"], 12), "ca_ab325", "not_yet_effective", "applies"),
  },
  {
    change_id: "chg_t2", kind: "test", test_id: "T2", title: "Mailing city differs from legal city", test_type: "boundary",
    summary: b("Addresses mailed under a neighborhood name are matched to the city that legally contains them.", "Las direcciones con nombre de barrio se asignan a la ciudad que legalmente las contiene."),
    created_at: "2026-10-01T23:00:00Z", rule_ids: ["ma_186_15b"], compare: { on: "2026-10-01" },
    affected_count: 90, conflict_count: 0, expected_check: passed,
    affected: affectedFrom(["A0118", ...idsIn(["Boston"], 5)], "ma_186_15b", "none", "applies"),
  },
  {
    change_id: "chg_t3", kind: "test", test_id: "T3", title: "NJ FAIR Act meets local bans", test_type: "as_of",
    summary: b("When the FAIR Act takes effect, buildings already under a local ban are flagged for a possible conflict.", "Cuando entre en vigor la Ley FAIR, los edificios con una prohibición local se marcan por posible conflicto."),
    created_at: "2026-10-01T23:00:00Z", rule_ids: ["nj_fair_act", "hob_ch158"], compare: { before: "2027-06-30", after: "2027-07-01" },
    affected_count: 140, conflict_count: 90, expected_check: passed,
    affected: affectedFrom(idsIn(["Hoboken", "Newark", "Jersey City"], 10), "nj_fair_act", "not_yet_effective", "applies", true),
  },
  {
    change_id: "chg_t4", kind: "test", test_id: "T4", title: "Pending Massachusetts bills", test_type: "pending",
    summary: b("Proposed bills are shown as proposals and never counted as law.", "Los proyectos de ley se muestran como propuestas y nunca se cuentan como ley."),
    created_at: "2026-10-01T23:00:00Z", rule_ids: ["ma_s2983", "ma_h5222"], compare: { mode: "with_without", on: "2026-10-01" },
    affected_count: 110, conflict_count: 0, expected_check: passed,
    affected: affectedFrom(idsIn(["Boston", "Cambridge", "Somerville"], 9), "ma_s2983", "none", "pending"),
  },
  {
    change_id: "chg_t5", kind: "test", test_id: "T5", title: "Massachusetts rent control stays barred", test_type: "negative",
    summary: b("No Massachusetts address gains a rent-increase rule.", "Ninguna dirección de Massachusetts obtiene una regla de aumento de renta."),
    created_at: "2026-10-01T23:00:00Z", rule_ids: [], compare: { on: "2026-10-01" },
    affected_count: 0, conflict_count: 0, expected_check: passed, affected: [],
  },
];

// ---------- proof ----------
export function proof(): ProofResponse {
  return {
    data_version: DATA_VERSION,
    compiled_at: COMPILED_AT,
    selfscore: {
      components: [
        { name: "Quote verification", score: 28, max: 30, note: "Quotes matched character for character" },
        { name: "Change checks", score: 20, max: 20, note: "All five tests match their definitions" },
        { name: "Geography", score: 17, max: 20, note: "A few addresses resolved by fallback geocoder" },
        { name: "Plain language", score: 13, max: 15, note: "Spanish coverage complete" },
      ],
      key: "silver",
      raw_report: "Sample self-score report.",
    },
    change_checks: CHANGES.map((c) => ({
      test_id: c.test_id ?? c.change_id, passed: true, affected: c.affected_count, expected: c.affected_count,
      conflicts: c.conflict_count, expected_conflicts: c.conflict_count,
    })),
    verification: { rules: allRules().length, tier_counts: { A: 16, B: 2, C: 1, C1: 0 }, quotes_verified: 18, rejected_candidates: 7, adjudicated_fields: 3, mean_confidence: 0.89 },
    facts: { derived_units: 41, record_conflicts: 6, zip_suspect: 3, missing_year_built: 22 },
    geo: { matched_batch: 471, matched_oneline: 19, matched_nominatim: 7, unmatched: 3, mailing_mismatches: 38, census_disagreements: 2 },
    plain_language: { mean_grade_en: 7.4, max_grade_en: 9.8, es_coverage: 1 },
    latency: { measured_at: "2026-10-01T23:05:00Z", lookup_p50_ms: 42, lookup_p95_ms: 118, custom_p50_ms: 61, llm_baseline_ms: null },
    cost: { total_usd: 18.42, by_stage: { extract: 11.2, verify: 4.1, explain: 3.12 } },
    open_questions: OPEN_QUESTIONS,
    limitations: [
      b("Owner type is not public, so owner-based exemptions are not checked.", "El tipo de propietario no es público, así que no se revisan exenciones por propietario."),
      b("Year built stands in for the certificate-of-occupancy date.", "El año de construcción sustituye la fecha del certificado de ocupación."),
    ],
  };
}

// ---------- ingest ----------
const STAGES: { stage: IngestStage; detail: string }[] = [
  { stage: "received", detail: "Document received" },
  { stage: "sectionize", detail: "Split into 6 sections" },
  { stage: "triage", detail: "2 sections contain rules" },
  { stage: "extract", detail: "Extracted 1 rule" },
  { stage: "verify", detail: "4 of 4 quotes found in the document" },
  { stage: "crosscheck", detail: "No contradicting rules found" },
  { stage: "calendar", detail: "Effective date computed: 2027-01-01" },
  { stage: "link", detail: "Linked to City of Cambridge" },
  { stage: "explain", detail: "Plain-language summary written in English and Spanish" },
  { stage: "diff", detail: "1 rule added" },
  { stage: "impact", detail: "50 addresses affected, 0 conflicts" },
  { stage: "ready", detail: "Ready to publish" },
];

const INGEST_RULE: RuleDef = {
  id: "cam_screening_2027",
  category: "screening_restrictions",
  title: "Cambridge Fair Screening Ordinance (ch. 8.68)",
  jur: JURIS.cam,
  eff: "2027-01-01",
  status: "not_yet_effective",
  requirement: "Limits use of eviction records in tenant screening.",
  summary: b("Landlords will not be able to reject applicants based on sealed eviction records.", "Los propietarios no podrán rechazar solicitantes por registros de desalojo sellados."),
  who: b("Applicants for rentals in Cambridge.", "Solicitantes de alquileres en Cambridge."),
  coverage: b("Residential rentals in Cambridge.", "Alquileres residenciales en Cambridge."),
  citation: cite("cam_ch_8_68", "Cambridge Mun. Code § 8.68.030", "No housing provider shall deny tenancy to any applicant on the basis of a sealed eviction record."),
};

export const jobs = new Map<string, IngestJob>();

export function createJob(): IngestJob {
  const job_id = `job_${Date.now().toString(36)}`;
  const job: IngestJob = {
    job_id, status: "running", stage: "received", started_at: new Date().toISOString(), finished_at: null,
    stages: STAGES.map((s) => ({ stage: s.stage, status: "pending", detail: s.detail, ms: null })),
    result: null, error: null,
  };
  jobs.set(job_id, job);
  return job;
}

export function runJob(job: IngestJob, onEvent: (e: { type: "stage" | "impact" | "done" | "error"; data: unknown }) => void): () => void {
  let cancelled = false;
  let i = 0;
  const step = () => {
    if (cancelled) return;
    if (i >= job.stages.length) {
      job.status = "ready";
      job.finished_at = new Date().toISOString();
      job.result = {
        rules: [ruleDetail(INGEST_RULE)], findings: [], relations: [],
        impact: { affected_count: 50, sample: affectedFrom(["A0009", ...idsIn(["Cambridge"], 4)], INGEST_RULE.id, "none", "not_yet_effective"), effective_date: "2027-01-01", conflicts: 0 },
        verification: { quotes_checked: 4, quotes_verified: 4, rejected: 0 }, cost_usd: 0.42, cache_hit: false,
      };
      onEvent({ type: "done", data: job });
      return;
    }
    const s = job.stages[i]!;
    s.status = "done";
    s.ms = 400 + (hash(s.stage) % 500);
    job.stage = s.stage;
    if (job.stages[i + 1]) job.stages[i + 1]!.status = "running";
    onEvent({ type: s.stage === "impact" ? "impact" : "stage", data: { ...s } });
    i += 1;
    setTimeout(step, 400 + Math.random() * 500);
  };
  job.stages[0]!.status = "running";
  setTimeout(step, 400 + Math.random() * 500);
  return () => { cancelled = true; };
}

export function publishJob(jobId: string) {
  const job = jobs.get(jobId);
  if (!job) return null;
  job.status = "published";
  job.stage = "published";
  if (!extraRules.some((r) => r.id === INGEST_RULE.id)) {
    extraRules.push(INGEST_RULE);
    extraBreakpoints["A0009"] = [{ date: "2027-01-01", rule_ids: [INGEST_RULE.id] }];
    CHANGES.unshift({
      change_id: "chg_ing_demo", kind: "ingest", test_id: null, title: "Cambridge Fair Screening Ordinance published", test_type: "as_of",
      summary: INGEST_RULE.summary, created_at: new Date().toISOString(), rule_ids: [INGEST_RULE.id], compare: { before: "2026-12-31", after: "2027-01-01" },
      affected_count: 50, conflict_count: 0, expected_check: null,
      affected: affectedFrom(["A0009", ...idsIn(["Cambridge"], 4)], INGEST_RULE.id, "none", "applies"),
    });
  }
  return { change_id: "chg_ing_demo", published_at: new Date().toISOString() };
}

export { sha };
