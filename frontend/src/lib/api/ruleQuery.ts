import type { RuleDetail } from "./types";

const STATE_NAMES: Record<string, string> = { CA: "California", NJ: "New Jersey", MA: "Massachusetts" };
const STOPWORDS = new Set(["rule", "rules", "law", "laws", "in", "of", "the", "for", "and", "a", "an", "on", "state"]);

/** Same parsing as the API: state names or codes become a state filter, the rest must all match. */
export function parseRuleQuery(raw: string) {
  let text = raw.toLowerCase().trim();
  const states = new Set<string>();
  for (const [code, name] of Object.entries(STATE_NAMES)) {
    const re = new RegExp(`\\b${name.toLowerCase()}\\b`, "g");
    if (re.test(text)) {
      states.add(code);
      text = text.replace(re, " ");
    }
  }
  const terms: string[] = [];
  for (const tok of text.match(/[\p{L}\p{N}_.§'-]+/gu) ?? []) {
    if (STATE_NAMES[tok.toUpperCase()]) states.add(tok.toUpperCase());
    else if (!STOPWORDS.has(tok)) terms.push(tok);
  }
  return { states, terms };
}

export function ruleSearchText(parts: { id: string; title: string; requirement: string; cite: string; jurName: string; jurLabel: string; state: string; category: string; extra?: string[] }) {
  return [parts.id, parts.title, parts.requirement, parts.cite, parts.jurName, parts.jurLabel, STATE_NAMES[parts.state] ?? "", parts.category.replace(/_/g, " "), ...(parts.extra ?? [])]
    .join(" ")
    .toLowerCase();
}

export interface RuleFilterInput {
  state?: string;
  jurisdiction_id?: string;
  category?: string;
  status?: string;
  tier?: string;
  q?: string;
}

/** Client-side equivalent of GET /v1/rules filtering, for static snapshot data. */
export function filterRules(rules: RuleDetail[], f: RuleFilterInput): RuleDetail[] {
  const { states, terms } = parseRuleQuery(f.q ?? "");
  return rules.filter((r) => {
    if (f.state && r.jurisdiction.state !== f.state) return false;
    if (states.size && !states.has(r.jurisdiction.state)) return false;
    if (f.jurisdiction_id && r.jurisdiction.id !== f.jurisdiction_id) return false;
    if (f.category && r.category !== f.category) return false;
    if (f.status && r.rule_status !== f.status) return false;
    if (f.tier && r.citation.tier !== f.tier) return false;
    if (!terms.length) return true;
    const hay = ruleSearchText({
      id: r.rule_id, title: r.title, requirement: r.requirement, cite: r.citation.cite,
      jurName: r.jurisdiction.name, jurLabel: r.jurisdiction.label, state: r.jurisdiction.state, category: r.category,
    });
    return terms.every((t) => hay.includes(t));
  });
}
