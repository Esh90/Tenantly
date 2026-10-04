"""Signal score (PLAN.md 9.2): how much of a capture is actual legal or housing text.

score = (kept lines of at least MIN_LINE characters that contain legal or housing vocabulary)
        / (kept non-empty lines)

"Kept" means not masked as boilerplate. A score below LOW_SIGNAL marks the document
``low_signal`` (the UI shows "Partial capture"). The vocabulary is general; it is not tuned to
any document.
"""

from __future__ import annotations

import re

from engine.corpus.boilerplate import MaskedDoc

MIN_LINE = 40
LOW_SIGNAL = 0.15

VOCAB = re.compile(
    r"\b(tenants?|landlords?|lessors?|lessees?|rents?|rental|rentals|evict\w*|leases?|deposits?"
    r"|housing|dwellings?|premises|tenancy|tenancies|residential|apartments?|ordinance|statute"
    r"|shall|algorithm\w*|pricing|unlawful|prohibit\w*|section|chapter|act)\b",
    re.I,
)


def signal_score(masked: MaskedDoc) -> float:
    kept = masked.kept_lines()
    if not kept:
        return 0.0
    hits = sum(1 for ln in kept if len(ln.text.strip()) >= MIN_LINE and VOCAB.search(ln.text))
    return hits / len(kept)


def is_low_signal(score: float) -> bool:
    return score < LOW_SIGNAL
