"""Central configuration: paths, model ids and policy switches (env-overridable)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")

DATASET = ROOT / "dataset"
SUPPLEMENT = ROOT / "dataset_supplement"
ARTIFACTS = ROOT / "artifacts"
OUT = ROOT / "out"

MANIFEST_CSV = DATASET / "corpus" / "corpus_manifest.csv"
LINKS_ONLY_CSV = DATASET / "corpus" / "links_only.csv"
TEXT_DIR = DATASET / "corpus" / "text"
ADDRESSES_CSV = DATASET / "data" / "sample_addresses.csv"
RULE_SCHEMA = DATASET / "schema" / "rule_record.schema.json"
CHANGE_TESTS = DATASET / "dev" / "change_tests.json"

MODEL_FAST = os.environ.get("MODEL_FAST", "claude-haiku-4-5-20251001")
MODEL_STRONG = os.environ.get("MODEL_STRONG", "claude-sonnet-5-5")
MODEL_JUDGE = os.environ.get("MODEL_JUDGE", "claude-opus-5-5")
BUDGET_USD_CAP = min(float(os.environ.get("BUDGET_USD_CAP", "18")), 18.0)

DEFAULT_AS_OF = os.environ.get("DEFAULT_AS_OF", "2026-10-01")
SOURCES_RETRIEVED_AT = os.environ.get("SOURCES_RETRIEVED_AT", "2026-10-01")
AS_OF_RANGE = ("2025-01-01", "2028-12-31")

EXEMPTION_MISSING_FACT = os.environ.get("EXEMPTION_MISSING_FACT", "caveat")
PROXY_CO_FROM_YEAR_BUILT = os.environ.get("PROXY_CO_FROM_YEAR_BUILT", "calendar_year")
CONFLICT_FLAG_MODE = os.environ.get("CONFLICT_FLAG_MODE", "explicit_only")
TIER_C_MIN_SIGNALS = int(os.environ.get("TIER_C_MIN_SIGNALS", "2"))

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "change-me")
ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o]
DEMO_MODE = os.environ.get("DEMO_MODE", "live")

DISCLAIMER = (
    "Tenantly shows public housing law for information only. It is not legal advice. "
    "Check the official source or a qualified professional before acting."
)
