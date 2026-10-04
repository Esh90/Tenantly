export const en = {
  skip: "Skip to main content",
  nav_rules: "Rules",
  nav_changes: "Changes",
  nav_about: "About",
  nav_watched: "Watched",
  nav_proof: "How we know",
  nav_menu: "Menu",
  nav_home: "Home",
  theme_toggle: "Switch color theme",
  lang_label: "Language",
  search_label: "Apartment address",
  search_placeholder: "Street address, city or ZIP",
  search_compact_placeholder: "Look up another address",
  search_submit: "Look up address",
  search_none: "No sample building matches that address.",
  search_hint: "Try a street name, a city, or a ZIP code.",
  search_loading: "Loading sample addresses",
  disclaimer:
    "Information, not legal advice. Check the official source or a qualified professional before acting.",
  footer_about:
    "Tenantly shows which housing laws reach an apartment address on a given date, and quotes the official text for every rule.",
  footer_data: "Data version",
  footer_compiled: "Compiled",
  footer_retrieved: "Sources retrieved October 1, 2026",
  footer_sample: "Sample data. Not legal information.",
  footer_explore: "Explore",
  footer_trust: "Trust",
  fallback_banner:
    "The live service is not responding. You are seeing the most recent saved snapshot.",
  home_title: "Which housing laws reach your apartment?",
  home_lede:
    "Enter an address. Tenantly finds the city it legally sits in, checks the building's public records, and quotes the official law text behind every rule that applies on the date you choose.",
  home_examples: "Try a sample building",
  home_how_title: "How Tenantly reads an address",
  home_step1_title: "Find the legal city",
  home_step1_body:
    "Mailing names can mislead. A Dorchester address is legally in Boston, so Boston's rules are the ones that reach it.",
  home_step2_title: "Check the building",
  home_step2_body:
    "Year built and unit count come from the assessor's roll. When a fact is missing, Tenantly says so instead of guessing.",
  home_step3_title: "Quote the law",
  home_step3_body:
    "Every rule links to the exact words in the official text, with the date it takes effect and what it overrides.",
  home_coverage_title: "Where Tenantly looks",
  home_coverage_body:
    "Three states and ten cities, tested on 500 real sample buildings. Six topics: rent increases, eviction protections, security deposits, application fees, tenant screening, and rent-setting software.",
  home_photo_caption: "Multifamily housing, the buildings Tenantly's sample is drawn from.",
  page_next: "This page is being built next.",
  notfound_title: "We couldn't find that page.",
  notfound_body: "The link may be out of date. You can look up an address from the home page.",
  go_home: "Go to the home page",
  lookup_legal_city: "Legal city",
  lookup_loading: "Reading the law for this address",
  lookup_error: "The lookup did not load.",
  try_again: "Try again",
} as const;

export type StringKey = keyof typeof en;
