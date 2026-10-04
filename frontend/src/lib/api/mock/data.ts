// Illustrative mock data shaped like the real API. Not legal information.
import type {
  AddressIndexItem,
  Bilingual,
  Category,
  Citation,
  EvidenceTier,
  Jurisdiction,
  KeyValue,
  RuleStatus,
  StateCode,
} from "../types";

export const b = (en: string, es: string): Bilingual => ({ en, es });

export const CATEGORIES: { key: Category; label: Bilingual }[] = [
  { key: "rent_increase_limits", label: b("Rent increases", "Aumentos de renta") },
  { key: "just_cause_eviction", label: b("Eviction protections", "Protección contra desalojos") },
  { key: "security_deposits", label: b("Security deposits", "Depósitos de seguridad") },
  { key: "application_screening_fees", label: b("Application fees", "Cuotas de solicitud") },
  { key: "screening_restrictions", label: b("Tenant screening", "Evaluación de inquilinos") },
  { key: "algorithmic_rent_setting", label: b("Rent-setting software", "Software para fijar rentas") },
];

export const RANGE = { start: "2025-01-01", end: "2028-12-31" };
export const DATA_VERSION = "2026.10.01-mock";
export const COMPILED_AT = "2026-10-01T23:10:00Z";
export const RETRIEVED_AT = "2026-10-01T22:35Z";
export const DISCLAIMER =
  "Information, not legal advice. Check the official source or a qualified professional before acting.";

// ---------- deterministic helpers ----------
export function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
export function sha(s: string): string {
  let out = "";
  let seed = hash(s);
  while (out.length < 64) {
    seed = Math.imul(seed ^ (seed >>> 13), 1597334677) >>> 0;
    out += seed.toString(16).padStart(8, "0");
  }
  return out.slice(0, 64);
}

// ---------- jurisdictions ----------
const J = (
  id: string,
  level: Jurisdiction["level"],
  name: string,
  label: string,
  state: StateCode,
  geoid: string | null,
): Jurisdiction => ({ id, level, name, label, state, geoid, in_scope: true });

export const JURIS = {
  CA: J("ca", "state", "California", "State of California", "CA", "06"),
  NJ: J("nj", "state", "New Jersey", "State of New Jersey", "NJ", "34"),
  MA: J("ma", "state", "Massachusetts", "Commonwealth of Massachusetts", "MA", "25"),
  sf_county: J("ca_sf_county", "county", "San Francisco", "City and County of San Francisco", "CA", "06075"),
  la_county: J("ca_la_county", "county", "Los Angeles", "Los Angeles County", "CA", "06037"),
  sd_county: J("ca_sd_county", "county", "San Diego", "San Diego County", "CA", "06073"),
  alameda: J("ca_alameda", "county", "Alameda", "Alameda County", "CA", "06001"),
  hudson: J("nj_hudson", "county", "Hudson", "Hudson County", "NJ", "34017"),
  essex: J("nj_essex", "county", "Essex", "Essex County", "NJ", "34013"),
  suffolk: J("ma_suffolk", "county", "Suffolk", "Suffolk County", "MA", "25025"),
  middlesex: J("ma_middlesex", "county", "Middlesex", "Middlesex County", "MA", "25017"),
  sf: J("ca_san_francisco", "city", "San Francisco", "City of San Francisco", "CA", "0667000"),
  la: J("ca_los_angeles", "city", "Los Angeles", "City of Los Angeles", "CA", "0644000"),
  sd: J("ca_san_diego", "city", "San Diego", "City of San Diego", "CA", "0666000"),
  oak: J("ca_oakland", "city", "Oakland", "City of Oakland", "CA", "0653000"),
  hob: J("nj_hoboken", "city", "Hoboken", "City of Hoboken", "NJ", "3432250"),
  nwk: J("nj_newark", "city", "Newark", "City of Newark", "NJ", "3451000"),
  jc: J("nj_jersey_city", "city", "Jersey City", "City of Jersey City", "NJ", "3436000"),
  bos: J("ma_boston", "city", "Boston", "City of Boston", "MA", "2507000"),
  cam: J("ma_cambridge", "city", "Cambridge", "City of Cambridge", "MA", "2511000"),
  som: J("ma_somerville", "city", "Somerville", "City of Somerville", "MA", "2562535"),
} as const;

export interface CityInfo {
  city: Jurisdiction;
  county: Jurisdiction;
  state: Jurisdiction;
  center: [number, number]; // [lat, lon]
}
export const CITIES: Record<string, CityInfo> = {
  "San Francisco": { city: JURIS.sf, county: JURIS.sf_county, state: JURIS.CA, center: [37.7749, -122.4194] },
  "Los Angeles": { city: JURIS.la, county: JURIS.la_county, state: JURIS.CA, center: [34.0522, -118.2437] },
  "San Diego": { city: JURIS.sd, county: JURIS.sd_county, state: JURIS.CA, center: [32.7157, -117.1611] },
  Oakland: { city: JURIS.oak, county: JURIS.alameda, state: JURIS.CA, center: [37.8044, -122.2712] },
  Hoboken: { city: JURIS.hob, county: JURIS.hudson, state: JURIS.NJ, center: [40.744, -74.0324] },
  Newark: { city: JURIS.nwk, county: JURIS.essex, state: JURIS.NJ, center: [40.7357, -74.1724] },
  "Jersey City": { city: JURIS.jc, county: JURIS.hudson, state: JURIS.NJ, center: [40.7178, -74.0431] },
  Boston: { city: JURIS.bos, county: JURIS.suffolk, state: JURIS.MA, center: [42.3601, -71.0589] },
  Cambridge: { city: JURIS.cam, county: JURIS.middlesex, state: JURIS.MA, center: [42.3736, -71.1097] },
  Somerville: { city: JURIS.som, county: JURIS.middlesex, state: JURIS.MA, center: [42.3876, -71.0995] },
};
export const cityOf = (n: string): CityInfo => CITIES[n] as CityInfo;
export const ALL_JURISDICTIONS: Jurisdiction[] = Object.values(JURIS);

// ---------- citations ----------
export function cite(
  doc_id: string,
  citeText: string,
  quote: string,
  opts: Partial<Citation> = {},
): Citation {
  const tier: EvidenceTier = opts.tier ?? "A";
  const prefix = 214 + (hash(doc_id) % 900);
  return {
    doc_id,
    cite: citeText,
    url: `https://example.gov/law/${doc_id}`,
    retrieved_at: RETRIEVED_AT,
    quote,
    char_start: tier === "C" ? null : prefix,
    char_end: tier === "C" ? null : prefix + quote.length,
    doc_sha256: sha(doc_id),
    tier,
    quote_source: "corpus",
    supplementary_doc: null,
    version_label: null,
    low_signal: false,
    ...opts,
  };
}

// ---------- rule definitions ----------
export interface Facts {
  year_built: number | null;
  units: number | null;
  subsidized: boolean | null;
}

export interface RuleDef {
  id: string;
  category: Category;
  title: string;
  jur: Jurisdiction;
  eff: string | null; // ISO date it takes effect
  status: RuleStatus;
  requirement: string;
  summary: Bilingual;
  who: Bilingual;
  coverage: Bilingual;
  citation: Citation;
  key_values?: KeyValue[];
  governs_over?: string[];
  supersede_reason?: Bilingual;
  open_question_ids?: string[];
  confidence?: number;
  review_flag?: boolean;
  penalty?: string | null;
  caveats?: Bilingual[];
  conflict?: { with_rule_id: string; active_from: string; explanation: Bilingual };
  /** Coverage test. Missing = covers every rental in the jurisdiction. */
  coverage_test?: (f: Facts, asOf: string) => CoverageOutcome;
}

export interface CoverageOutcome {
  covered: boolean | null; // null = cannot tell
  conditions: import("../types").ConditionTrace[];
  missing: string[];
}

const builtLabel = (y: number | null) => (y == null ? null : `Built ${y}`);

function builtOnOrBefore(cutoff: string, labelEn: string, labelEs: string) {
  return (f: Facts): CoverageOutcome => {
    const cutoffYear = Number(cutoff.slice(0, 4));
    const r: "true" | "false" | "unknown" =
      f.year_built == null ? "unknown" : f.year_built <= cutoffYear ? "true" : "false";
    return {
      covered: r === "unknown" ? null : r === "true",
      missing: r === "unknown" ? ["year_built"] : [],
      conditions: [
        {
          label: b(labelEn, labelEs),
          fact: "year_built",
          op: "<=",
          expected: `on or before ${cutoff}`,
          actual: builtLabel(f.year_built),
          basis: f.year_built == null ? null : "Year built from assessor records",
          result: r,
        },
      ],
    };
  };
}

function rolling15(f: Facts, asOf: string): CoverageOutcome {
  const cutoffYear = Number(asOf.slice(0, 4)) - 15;
  const r: "true" | "false" | "unknown" =
    f.year_built == null ? "unknown" : f.year_built <= cutoffYear ? "true" : "false";
  return {
    covered: r === "unknown" ? null : r === "true",
    missing: r === "unknown" ? ["year_built"] : [],
    conditions: [
      {
        label: b(
          "Certificate of occupancy issued more than 15 years ago",
          "Certificado de ocupación emitido hace más de 15 años",
        ),
        fact: "year_built",
        op: "<=",
        expected: `${cutoffYear} or earlier`,
        actual: builtLabel(f.year_built),
        basis: f.year_built == null ? null : "Year built stands in for the certificate-of-occupancy date",
        result: r,
      },
    ],
  };
}

function smallLandlordRuledOut(f: Facts): CoverageOutcome {
  const r: "true" | "false" | "unknown" = f.units == null ? "unknown" : f.units > 4 ? "true" : "unknown";
  return {
    covered: true,
    missing: [],
    conditions: [
      {
        label: b(
          "Small-landlord exception does not apply",
          "La excepción para pequeños propietarios no aplica",
        ),
        fact: "units",
        op: ">",
        expected: "more than 4 units",
        actual: f.units == null ? null : `${f.units} units (exception requires 4 or fewer)`,
        basis: "Unit count from public records",
        result: r,
      },
    ],
  };
}

function subsidyUnknown(f: Facts): CoverageOutcome {
  const r: "true" | "false" | "unknown" =
    f.subsidized == null ? "unknown" : f.subsidized ? "true" : "false";
  return {
    covered: r === "unknown" ? null : r === "true",
    missing: r === "unknown" ? ["subsidized_or_affordable"] : [],
    conditions: [
      {
        label: b("Unit is subsidized or affordable housing", "La unidad es vivienda subsidiada o asequible"),
        fact: "subsidized_or_affordable",
        op: "==",
        expected: "true",
        actual: f.subsidized == null ? null : String(f.subsidized),
        basis: null,
        result: r,
      },
    ],
  };
}

const allRentals = b("Most residential rental units in the jurisdiction.", "La mayoría de las unidades de alquiler residencial en la jurisdicción.");

export const RULES: RuleDef[] = [
  // ----- California -----
  {
    id: "ca_civ_1947_12",
    category: "rent_increase_limits",
    title: "Cal. Civ. Code § 1947.12 (statewide rent cap)",
    jur: JURIS.CA,
    eff: "2020-01-01",
    status: "in_force",
    requirement: "Limits yearly rent increases to 5% plus local inflation, never more than 10%.",
    summary: b(
      "Rent can go up at most 5% plus local inflation in 12 months, and never more than 10%.",
      "La renta puede subir como máximo 5% más la inflación local en 12 meses, y nunca más de 10%.",
    ),
    who: b("Buildings with a certificate of occupancy more than 15 years old.", "Edificios con certificado de ocupación de más de 15 años."),
    coverage: b("Residential units more than 15 years old, with listed exemptions.", "Unidades residenciales de más de 15 años, con exenciones."),
    citation: cite(
      "ca_civ_1947_12",
      "Cal. Civ. Code § 1947.12(a)(1)",
      "an owner of residential real property shall not, over the course of any 12-month period, increase the gross rental rate for a dwelling or a unit more than 5 percent plus the percentage change in the cost of living, or 10 percent, whichever is lower",
    ),
    key_values: [{ name: "Maximum increase", text: "5% plus CPI, capped at 10%", valid_from: null, valid_to: null, stale: false, stale_note: null }],
    coverage_test: rolling15,
    supersede_reason: b(
      "The state cap yields to the local ordinance for this building.",
      "El tope estatal cede ante la ordenanza local para este edificio.",
    ),
  },
  {
    id: "ca_civ_1946_2",
    category: "just_cause_eviction",
    title: "Cal. Civ. Code § 1946.2 (Tenant Protection Act)",
    jur: JURIS.CA,
    eff: "2020-01-01",
    status: "in_force",
    requirement: "Requires a listed just cause to end a tenancy after 12 months.",
    summary: b(
      "After 12 months, a landlord needs one of the listed reasons to end the tenancy.",
      "Después de 12 meses, el propietario necesita una de las razones enumeradas para terminar el contrato.",
    ),
    who: b("Tenants who have lived in the unit 12 months or more.", "Inquilinos que han vivido en la unidad 12 meses o más."),
    coverage: b("Residential units more than 15 years old, with listed exemptions.", "Unidades residenciales de más de 15 años, con exenciones."),
    citation: cite(
      "ca_civ_1946_2",
      "Cal. Civ. Code § 1946.2(a)",
      "after a tenant has continuously and lawfully occupied a residential real property for 12 months, the owner of the residential real property shall not terminate the tenancy without just cause, which shall be stated in the written notice to terminate tenancy",
    ),
    coverage_test: rolling15,
    supersede_reason: b(
      "The state rule yields to the local eviction ordinance for this building.",
      "La regla estatal cede ante la ordenanza local de desalojo para este edificio.",
    ),
  },
  {
    id: "ca_civ_1950_5",
    category: "security_deposits",
    title: "Cal. Civ. Code § 1950.5 (security deposits)",
    jur: JURIS.CA,
    eff: "2024-07-01",
    status: "in_force",
    requirement: "Caps the security deposit at one month of rent.",
    summary: b(
      "The security deposit cannot be more than one month of rent.",
      "El depósito de seguridad no puede ser mayor a un mes de renta.",
    ),
    who: b("Tenants of residential property.", "Inquilinos de propiedades residenciales."),
    coverage: allRentals,
    citation: cite(
      "ca_civ_1950_5",
      "Cal. Civ. Code § 1950.5(c)(1)",
      "A landlord may not demand or receive security, however denominated, in an amount or value in excess of an amount equal to one month's rent, in addition to any rent for the first month paid on or before initial occupancy.",
    ),
    key_values: [{ name: "Deposit limit", text: "One month of rent", valid_from: "2024-07-01", valid_to: null, stale: false, stale_note: null }],
    coverage_test: smallLandlordRuledOut,
  },
  {
    id: "ca_civ_1950_6",
    category: "application_screening_fees",
    title: "Cal. Civ. Code § 1950.6 (application screening fees)",
    jur: JURIS.CA,
    eff: "1997-01-01",
    status: "in_force",
    requirement: "Limits the application screening fee to $30, adjusted for inflation.",
    summary: b(
      "The application fee is limited to $30, adjusted each year for inflation, and must match actual costs.",
      "La cuota de solicitud está limitada a $30, ajustada cada año por inflación, y debe corresponder a costos reales.",
    ),
    who: b("Applicants for residential rentals.", "Solicitantes de alquileres residenciales."),
    coverage: allRentals,
    citation: cite(
      "ca_civ_1950_6",
      "Cal. Civ. Code § 1950.6(b)",
      "The amount of the application screening fee shall not be greater than the actual out-of-pocket costs of gathering information concerning the applicant, and in no case shall the fee exceed thirty dollars ($30), adjusted annually",
    ),
    key_values: [{ name: "Fee limit", text: "$30, adjusted for inflation", valid_from: null, valid_to: null, stale: false, stale_note: null }],
    open_question_ids: ["oq_ca_fee_figure"],
    confidence: 0.82,
  },
  {
    id: "ca_gov_12955",
    category: "screening_restrictions",
    title: "Cal. Gov. Code § 12955 (source of income)",
    jur: JURIS.CA,
    eff: "2020-01-01",
    status: "in_force",
    requirement: "Bars housing discrimination based on source of income, including vouchers.",
    summary: b(
      "Landlords cannot refuse applicants because of their source of income, including housing vouchers.",
      "Los propietarios no pueden rechazar solicitantes por su fuente de ingresos, incluidos los vales de vivienda.",
    ),
    who: b("Applicants and tenants.", "Solicitantes e inquilinos."),
    coverage: allRentals,
    citation: cite(
      "ca_gov_12955",
      "Cal. Gov. Code § 12955(a)",
      "It shall be unlawful for the owner of any housing accommodation to discriminate against or harass any person because of the race, color, religion, sex, gender, sexual orientation, marital status, national origin, ancestry, familial status, source of income, disability, or genetic information of that person.",
    ),
  },
  {
    id: "ca_ab325",
    category: "algorithmic_rent_setting",
    title: "AB 325 (Bus. & Prof. Code § 16729)",
    jur: JURIS.CA,
    eff: "2026-01-01",
    status: "in_force",
    requirement: "Bars using or distributing a common pricing algorithm to set rents.",
    summary: b(
      "Landlords cannot use a shared pricing algorithm with competitors to set rents.",
      "Los propietarios no pueden usar un algoritmo de precios compartido con competidores para fijar rentas.",
    ),
    who: b("All residential rentals in California.", "Todos los alquileres residenciales en California."),
    coverage: allRentals,
    citation: cite(
      "ca_ab325",
      "Cal. Bus. & Prof. Code § 16729(a)",
      "It shall be unlawful for a person to use or distribute a common pricing algorithm as part of a contract, combination in the form of a trust, or conspiracy to restrain trade or commerce.",
    ),
  },
  // ----- San Francisco -----
  {
    id: "sf_admin_37_3",
    category: "rent_increase_limits",
    title: "SF Rent Ordinance (S.F. Admin. Code § 37.3)",
    jur: JURIS.sf,
    eff: "1979-06-13",
    status: "in_force",
    requirement: "Limits yearly increases to the allowable percentage set by the Rent Board.",
    summary: b(
      "Rent can go up once a year by the Rent Board's allowable percentage.",
      "La renta puede subir una vez al año según el porcentaje permitido por la Junta de Renta.",
    ),
    who: b("Units with a certificate of occupancy on or before June 13, 1979.", "Unidades con certificado de ocupación hasta el 13 de junio de 1979."),
    coverage: b("Rental units first occupied on or before June 13, 1979.", "Unidades ocupadas por primera vez hasta el 13 de junio de 1979."),
    citation: cite(
      "sf_admin_37_3",
      "S.F. Admin. Code § 37.3(a)(1)",
      "Landlords may impose annual rent increases which do not exceed the tenant's base rent by more than the allowable annual increase set by the Board.",
    ),
    key_values: [
      { name: "Allowable increase", text: "1.6% allowable increase", valid_from: "2026-03-01", valid_to: "2027-02-28", stale: false, stale_note: null },
      { name: "Allowable increase", text: "1.7% allowable increase", valid_from: "2025-03-01", valid_to: "2026-02-28", stale: false, stale_note: null },
    ],
    governs_over: ["ca_civ_1947_12"],
    coverage_test: builtOnOrBefore(
      "1979-06-13",
      "Certificate of occupancy on or before June 13, 1979",
      "Certificado de ocupación hasta el 13 de junio de 1979",
    ),
  },
  {
    id: "sf_admin_37_9",
    category: "just_cause_eviction",
    title: "S.F. Admin. Code § 37.9 (just cause eviction)",
    jur: JURIS.sf,
    eff: "1979-06-13",
    status: "in_force",
    requirement: "Allows evictions only for listed just causes, from the start of the tenancy.",
    summary: b(
      "A landlord can only evict for one of the reasons listed in the ordinance.",
      "El propietario solo puede desalojar por una de las razones enumeradas en la ordenanza.",
    ),
    who: b("Most rental units in San Francisco.", "La mayoría de las unidades de alquiler en San Francisco."),
    coverage: allRentals,
    citation: cite(
      "sf_admin_37_9",
      "S.F. Admin. Code § 37.9(a)",
      "A landlord shall not endeavor to recover possession of a rental unit unless at least one of the following grounds is the landlord's dominant motive for recovering possession.",
    ),
    governs_over: ["ca_civ_1946_2"],
  },
  {
    id: "sf_fair_chance",
    category: "screening_restrictions",
    title: "SF Fair Chance Ordinance (Police Code Art. 49)",
    jur: JURIS.sf,
    eff: "2014-08-13",
    status: "in_force",
    requirement: "Limits use of arrest and conviction records in affordable housing screening.",
    summary: b(
      "Affordable housing providers cannot ask about certain arrest or conviction records.",
      "Los proveedores de vivienda asequible no pueden preguntar por ciertos antecedentes penales.",
    ),
    who: b("Applicants for affordable housing units.", "Solicitantes de unidades de vivienda asequible."),
    coverage: b("Affordable housing in San Francisco.", "Vivienda asequible en San Francisco."),
    citation: cite(
      "sf_police_art49",
      "S.F. Police Code § 4906",
      "Housing providers shall not, at any time, inquire about or require disclosure of an arrest not leading to a conviction.",
      { tier: "B", low_signal: true },
    ),
    caveats: [b("Partial capture of the official page.", "Captura parcial de la página oficial.")],
    coverage_test: subsidyUnknown,
    confidence: 0.68,
  },
  {
    id: "sf_admin_37_10c",
    category: "algorithmic_rent_setting",
    title: "S.F. Admin. Code § 37.10C (algorithmic rent setting)",
    jur: JURIS.sf,
    eff: "2024-09-27",
    status: "in_force",
    requirement: "Bars algorithmic devices that set rents or occupancy for multiple landlords.",
    summary: b(
      "Landlords cannot use software that coordinates rents across different landlords.",
      "Los propietarios no pueden usar software que coordine rentas entre distintos propietarios.",
    ),
    who: b("Residential rentals in San Francisco.", "Alquileres residenciales en San Francisco."),
    coverage: allRentals,
    citation: cite(
      "sf_admin_37_10c",
      "S.F. Admin. Code § 37.10C(b)",
      "It shall be unlawful for any person or entity to sell, license, or otherwise provide to two or more landlords an algorithmic device for the purpose of setting rents.",
    ),
  },
  // ----- Los Angeles -----
  {
    id: "la_rso",
    category: "rent_increase_limits",
    title: "LA Rent Stabilization Ordinance (LAMC § 151.06)",
    jur: JURIS.la,
    eff: "1978-10-01",
    status: "in_force",
    requirement: "Limits yearly increases to the percentage set by the city.",
    summary: b(
      "Rent can go up once every 12 months by the city's allowable percentage.",
      "La renta puede subir una vez cada 12 meses según el porcentaje permitido por la ciudad.",
    ),
    who: b("Units built on or before October 1, 1978.", "Unidades construidas hasta el 1 de octubre de 1978."),
    coverage: b("Rental units with a certificate of occupancy on or before October 1, 1978.", "Unidades con certificado de ocupación hasta el 1 de octubre de 1978."),
    citation: cite(
      "la_lamc_151_06",
      "LAMC § 151.06(D)",
      "No landlord shall demand or accept a rent for a rental unit in excess of the maximum adjusted rent permitted by this chapter.",
    ),
    key_values: [
      {
        name: "Allowable increase",
        text: "3%",
        valid_from: "2025-07-01",
        valid_to: null,
        stale: true,
        stale_note: b(
          "The figure for this date is not in our sources (last published: 3% through June 30, 2026).",
          "La cifra para esta fecha no está en nuestras fuentes (última publicada: 3% hasta el 30 de junio de 2026).",
        ),
      },
    ],
    governs_over: ["ca_civ_1947_12"],
    coverage_test: builtOnOrBefore("1978-10-01", "Built on or before October 1, 1978", "Construido hasta el 1 de octubre de 1978"),
  },
  // ----- San Diego -----
  {
    id: "sd_sdmc_98_0704",
    category: "just_cause_eviction",
    title: "SDMC § 98.0704 (Residential Tenant Protections)",
    jur: JURIS.sd,
    eff: "2023-06-23",
    status: "in_force",
    requirement: "Requires just cause to end a tenancy from the first day.",
    summary: b(
      "A landlord needs a listed reason to end the tenancy, starting on the first day.",
      "El propietario necesita una razón enumerada para terminar el contrato desde el primer día.",
    ),
    who: b("Units with a certificate of occupancy more than 15 years old.", "Unidades con certificado de ocupación de más de 15 años."),
    coverage: b("Residential units in San Diego, with listed exemptions.", "Unidades residenciales en San Diego, con exenciones."),
    citation: cite(
      "sd_sdmc_98_0704",
      "SDMC § 98.0704(a)",
      "A landlord shall not terminate a tenancy without just cause, which shall be stated in the written notice to terminate tenancy.",
    ),
    governs_over: ["ca_civ_1946_2"],
    coverage_test: rolling15,
  },
  // ----- Oakland -----
  {
    id: "oak_omc_8_22",
    category: "rent_increase_limits",
    title: "Oakland Rent Adjustment Program (O.M.C. § 8.22.070)",
    jur: JURIS.oak,
    eff: "1980-10-01",
    status: "in_force",
    requirement: "Limits yearly increases to the CPI-based allowance.",
    summary: b(
      "Rent can go up once a year by the city's CPI-based allowance.",
      "La renta puede subir una vez al año según el ajuste por inflación de la ciudad.",
    ),
    who: b("Units built before 1983.", "Unidades construidas antes de 1983."),
    coverage: b("Rental units with a certificate of occupancy before January 1, 1983.", "Unidades con certificado de ocupación antes del 1 de enero de 1983."),
    citation: cite(
      "oak_omc_8_22",
      "O.M.C. § 8.22.070(B)",
      "Rent may be increased once in any twelve month period by an amount equal to or less than the CPI rent adjustment.",
    ),
    governs_over: ["ca_civ_1947_12"],
    coverage_test: builtOnOrBefore("1982-12-31", "Built before 1983", "Construido antes de 1983"),
  },
  // ----- New Jersey -----
  {
    id: "nj_46_8_21_2",
    category: "security_deposits",
    title: "N.J.S.A. 46:8-21.2 (security deposits)",
    jur: JURIS.NJ,
    eff: "1971-06-01",
    status: "in_force",
    requirement: "Caps the security deposit at one and a half months of rent.",
    summary: b(
      "The security deposit cannot be more than one and a half months of rent.",
      "El depósito de seguridad no puede ser mayor a un mes y medio de renta.",
    ),
    who: b("Tenants of most residential rentals.", "Inquilinos de la mayoría de los alquileres residenciales."),
    coverage: allRentals,
    citation: cite(
      "nj_46_8_21_2",
      "N.J.S.A. 46:8-21.2",
      "No owner or lessee may require a security deposit in an amount in excess of one and one-half times one month's rent.",
    ),
  },
  {
    id: "nj_2a_18_61_1",
    category: "just_cause_eviction",
    title: "N.J.S.A. 2A:18-61.1 (Anti-Eviction Act)",
    jur: JURIS.NJ,
    eff: "1974-06-25",
    status: "in_force",
    requirement: "Allows removal only for listed good causes.",
    summary: b(
      "A tenant can only be removed for one of the good causes listed in the law.",
      "Un inquilino solo puede ser removido por una de las causas justificadas enumeradas en la ley.",
    ),
    who: b("Tenants of most residential rentals, except small owner-occupied buildings.", "Inquilinos de la mayoría de los alquileres, excepto edificios pequeños ocupados por el dueño."),
    coverage: allRentals,
    citation: cite(
      "nj_2a_18_61_1",
      "N.J.S.A. 2A:18-61.1",
      "No lessee or tenant may be removed by the Superior Court from any house, building, mobile home or land in a mobile home park or tenement leased for residential purposes, except upon establishment of one of the following grounds as good cause.",
    ),
  },
  {
    id: "nj_fair_act",
    category: "algorithmic_rent_setting",
    title: "NJ FAIR Act (P.L. 2026, c. 41)",
    jur: JURIS.NJ,
    eff: "2027-07-01",
    status: "not_yet_effective",
    requirement: "Bars algorithmic rent-setting tools that use competitor data.",
    summary: b(
      "Landlords will not be able to use rent-setting software that relies on competitors' private data.",
      "Los propietarios no podrán usar software para fijar rentas que use datos privados de competidores.",
    ),
    who: b("Residential rentals in New Jersey.", "Alquileres residenciales en Nueva Jersey."),
    coverage: allRentals,
    citation: cite(
      "nj_fair_act",
      "P.L. 2026, c. 41, § 3(a)",
      "A landlord shall not use, in setting rent or occupancy levels, any algorithmic device that uses nonpublic competitor data.",
    ),
    conflict: {
      with_rule_id: "hob_ch158",
      active_from: "2027-07-01",
      explanation: b(
        "The state act may preempt the Hoboken ban once both are in effect.",
        "La ley estatal podría prevalecer sobre la prohibición de Hoboken cuando ambas estén vigentes.",
      ),
    },
  },
  {
    id: "hob_ch158",
    category: "algorithmic_rent_setting",
    title: "Hoboken local ban (ch. 158, Art. II)",
    jur: JURIS.hob,
    eff: "2024-11-20",
    status: "in_force",
    requirement: "Bars algorithmic rent-setting software in Hoboken.",
    summary: b(
      "Landlords in Hoboken cannot use software to set rents with competitors' data.",
      "Los propietarios en Hoboken no pueden usar software para fijar rentas con datos de competidores.",
    ),
    who: b("Residential rentals in Hoboken.", "Alquileres residenciales en Hoboken."),
    coverage: allRentals,
    citation: cite(
      "hob_ch158",
      "Hoboken City Code ch. 158, Art. II",
      "No landlord shall use an algorithmic device to set rents within the City.",
      { tier: "C", quote_source: "supplementary", supplementary_doc: "challenge_brief_public.pdf" },
    ),
    confidence: 0.55,
    review_flag: true,
    conflict: {
      with_rule_id: "nj_fair_act",
      active_from: "2027-07-01",
      explanation: b(
        "The state FAIR Act may preempt this local ban once it takes effect.",
        "La Ley FAIR estatal podría prevalecer sobre esta prohibición local cuando entre en vigor.",
      ),
    },
  },
  // ----- Massachusetts -----
  {
    id: "ma_186_15b",
    category: "security_deposits",
    title: "M.G.L. c. 186 § 15B (security deposits)",
    jur: JURIS.MA,
    eff: "1978-01-01",
    status: "in_force",
    requirement: "Caps the security deposit at first month's rent and requires a separate account.",
    summary: b(
      "The security deposit cannot be more than one month of rent, and must be kept in a separate bank account.",
      "El depósito no puede ser mayor a un mes de renta y debe guardarse en una cuenta bancaria separada.",
    ),
    who: b("Tenants of residential rentals.", "Inquilinos de alquileres residenciales."),
    coverage: allRentals,
    citation: cite(
      "ma_186_15b",
      "M.G.L. c. 186 § 15B(1)(b)",
      "a lessor may require a security deposit not in excess of the amount of the first full month's rent.",
    ),
  },
  {
    id: "ma_186_15b_fees",
    category: "application_screening_fees",
    title: "M.G.L. c. 186 § 15B(1)(b) (fees at move-in)",
    jur: JURIS.MA,
    eff: "1978-01-01",
    status: "in_force",
    requirement: "Bars charging fees beyond first and last month, deposit, and a lock fee.",
    summary: b(
      "At move-in, a landlord cannot charge anything other than first and last month, a deposit, and a lock fee.",
      "Al mudarse, el propietario solo puede cobrar el primer y último mes, un depósito y el costo de cerradura.",
    ),
    who: b("Applicants and new tenants.", "Solicitantes y nuevos inquilinos."),
    coverage: allRentals,
    citation: cite(
      "ma_186_15b",
      "M.G.L. c. 186 § 15B(1)(b)",
      "a lessor shall not require a tenant or prospective tenant to pay any amount in excess of the following: rent for the first full month, rent for the last full month, a security deposit, and the purchase and installation cost for a new lock.",
    ),
  },
];

export const PENDING_MA = [
  {
    id: "ma_s2983",
    title: "S.2983 (algorithmic rent setting)",
    summary: b(
      "A Senate bill that would bar rent-setting software using competitor data. It is not law.",
      "Un proyecto del Senado que prohibiría software para fijar rentas con datos de competidores. No es ley.",
    ),
    citation: cite("ma_s2983", "Mass. S.2983, § 1", "No landlord shall employ a rent-setting algorithm that relies on nonpublic competitor data."),
  },
  {
    id: "ma_h5222",
    title: "H.5222 (algorithmic rent setting)",
    summary: b(
      "A House bill on rent-setting software. It is not law.",
      "Un proyecto de la Cámara sobre software para fijar rentas. No es ley.",
    ),
    citation: cite("ma_h5222", "Mass. H.5222, § 2", "The use of coordinated pricing software in residential leasing shall constitute an unfair practice."),
  },
];

// ---------- address index ----------
interface SeedAddr {
  id: string;
  label: string;
  street: string;
  postal: string;
  legal: string;
  zip: string | null;
  lat: number;
  lon: number;
  facts: Facts;
  assessor_derived_units?: string;
}

const SCENARIOS: SeedAddr[] = [
  { id: "A0001", label: "6238 DE LONGPRE AVE, Los Angeles, CA", street: "6238 DE LONGPRE AVE", postal: "Los Angeles", legal: "Los Angeles", zip: "90028", lat: 34.0966, lon: -118.3255, facts: { year_built: 1927, units: 32, subsidized: false } },
  { id: "A0002", label: "1031-1035 CLINTON ST, Hoboken, NJ", street: "1031-1035 CLINTON ST", postal: "Hoboken", legal: "Hoboken", zip: "07030", lat: 40.7505, lon: -74.029, facts: { year_built: 2001, units: 20, subsidized: false }, assessor_derived_units: "MOD-IV building description 6B-20U-G" },
  { id: "A0003", label: "876-878 S 14TH ST, Newark, NJ", street: "876-878 S 14TH ST", postal: "Newark", legal: "Newark", zip: "11219", lat: 40.738, lon: -74.201, facts: { year_built: 1910, units: 4, subsidized: false } },
  { id: "A0009", label: "322-322.5 WESTERN AVE, Cambridge, MA", street: "322-322.5 WESTERN AVE", postal: "Cambridge", legal: "Cambridge", zip: "02139", lat: 42.364, lon: -71.108, facts: { year_built: 1915, units: 6, subsidized: false } },
  { id: "A0016", label: "3515 FILLMORE ST, San Francisco, CA", street: "3515 FILLMORE ST", postal: "San Francisco", legal: "San Francisco", zip: "94123", lat: 37.8003, lon: -122.436, facts: { year_built: 1926, units: 21, subsidized: null } },
  { id: "A0019", label: "3820 HAINES ST, San Diego, CA", street: "3820 HAINES ST", postal: "San Diego", legal: "San Diego", zip: "92109", lat: 32.7976, lon: -117.235, facts: { year_built: null, units: 16, subsidized: false } },
  { id: "A0118", label: "18-34 KINGBIRD RD, Dorchester, MA", street: "18-34 KINGBIRD RD", postal: "Dorchester", legal: "Boston", zip: "02124", lat: 42.2728, lon: -71.0952, facts: { year_built: 1964, units: 18, subsidized: false } },
];

const STREETS: Record<string, string[]> = {
  "San Francisco": ["1450 GUERRERO ST", "780 FREDERICK ST", "2201 SACRAMENTO ST", "455 HYDE ST"],
  "Los Angeles": ["1120 N KINGSLEY DR", "3640 W 4TH ST", "4501 FINLEY AVE", "1717 N VISTA ST"],
  "San Diego": ["4040 HAWK ST", "3110 ADAMS AVE", "1835 COLUMBIA ST"],
  Oakland: ["560 VERNON ST", "3920 PIEDMONT AVE", "1501 HARRISON ST", "2830 E 16TH ST"],
  Hoboken: ["714 WASHINGTON ST", "301 GARDEN ST", "1200 BLOOMFIELD ST"],
  Newark: ["68 MT PROSPECT AVE", "425 HIGHLAND AVE", "17 ROSEVILLE AVE"],
  "Jersey City": ["255 PALISADE AVE", "88 MONTGOMERY ST", "540 BERGEN AVE", "17 BRIGHT ST"],
  Boston: ["120 COMMONWEALTH AVE", "45 PETERBOROUGH ST", "301 BOYLSTON ST"],
  Cambridge: ["1 FOLLEN ST", "35 INMAN ST", "212 HAMPSHIRE ST"],
  Somerville: ["44 SUMMER ST", "12 CENTRAL ST", "390 HIGHLAND AVE"],
};
const ZIPS: Record<string, string> = {
  "San Francisco": "94110", "Los Angeles": "90004", "San Diego": "92104", Oakland: "94610",
  Hoboken: "07030", Newark: "07104", "Jersey City": "07306", Boston: "02116", Cambridge: "02138", Somerville: "02143",
};

function generated(): SeedAddr[] {
  const out: SeedAddr[] = [];
  let n = 20;
  for (const [city, streets] of Object.entries(STREETS)) {
    const info = cityOf(city);
    streets.forEach((street, i) => {
      n += 3 + (i % 4);
      const id = `A${String(n).padStart(4, "0")}`;
      const h = hash(id);
      const years = [1908, 1924, 1931, 1949, 1962, 1974, 1986, 1999, 2008, 2015];
      out.push({
        id,
        label: `${street}, ${city}, ${info.state.id.toUpperCase()}`,
        street,
        postal: city,
        legal: city,
        zip: ZIPS[city] ?? null,
        lat: info.center[0] + (((h % 400) - 200) / 10000),
        lon: info.center[1] + ((((h >> 9) % 400) - 200) / 10000),
        facts: { year_built: years[h % years.length] ?? null, units: 2 + (h % 60), subsidized: false },
      });
    });
  }
  return out;
}

export const ADDRESSES: SeedAddr[] = [...SCENARIOS, ...generated()].sort((a, b2) => a.id.localeCompare(b2.id));
export type { SeedAddr };

export function stateOf(a: SeedAddr): StateCode {
  return cityOf(a.legal).state.state;
}

export const ADDRESS_INDEX: AddressIndexItem[] = ADDRESSES.map((a) => ({
  address_id: a.id,
  label: a.label,
  postal_city: a.postal,
  legal_city: a.legal,
  state: stateOf(a),
  zip: a.zip,
  lat: a.lat,
  lon: a.lon,
}));
