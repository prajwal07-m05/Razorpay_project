"""Central configuration for the CaseFile financial audit engine.

All thresholds, weights and base-confidence constants live here so the
engine is deterministic and easy to tune. Nothing here imports pandas or
fastapi; these are plain Python constants used by the engine core.
"""
import os


def _int_env(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _float_env(name, default):
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _bool_env(name, default=False):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Dataset generation (reproducible + configurable)
# ---------------------------------------------------------------------------
# Number of CANONICAL financial transactions (each expands into an order,
# a payment, optional refunds, a fee, a settlement and a bank credit).
DATASET_SIZE = _int_env("CASEFILE_DATASET_SIZE", 100000)
# Seed for deterministic generation: same seed + size => identical dataset.
SEED = _int_env("CASEFILE_SEED", 42)
# Fraction of the *bulk* (non-curated) transactions that get an injected
# anomaly. The first 15 transactions are hand-curated planted anomalies.
ANOMALY_RATE = _float_env("CASEFILE_ANOMALY_RATE", 0.01)

# ---------------------------------------------------------------------------
# Runtime guardrails
# ---------------------------------------------------------------------------
# Cap on how many (priority-ranked) cases the audit/run endpoint returns to
# the browser. The full set is always available via the paginated /api/cases.
MAX_CASES_RETURNED = _int_env("CASEFILE_MAX_CASES", 500)
DEFAULT_PAGE_SIZE = _int_env("CASEFILE_PAGE_SIZE", 50)
# When true, an AI-provider failure surfaces "AI INVESTIGATION UNAVAILABLE"
# instead of silently returning deterministic fallback reasoning. REQUIRE_CLAUDE
# is honoured as a legacy alias so older deployments keep working.
REQUIRE_CLAUDE = _bool_env("REQUIRE_CLAUDE", False)
REQUIRE_AI = _bool_env("REQUIRE_AI", REQUIRE_CLAUDE)
# Deterministic fallback is opt-in only. When a real provider is selected it is
# NEVER auto-swapped for the fallback on failure unless this is explicitly set.
ALLOW_AI_FALLBACK = _bool_env("ALLOW_AI_FALLBACK", False)

# ---------------------------------------------------------------------------
# Anomaly types
# ---------------------------------------------------------------------------
MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
DUPLICATE_PAYMENT = "DUPLICATE_PAYMENT"
REFUND_EXCEEDS_PAYMENT = "REFUND_EXCEEDS_PAYMENT"
STATUS_MISMATCH = "STATUS_MISMATCH"
MISSING_BANK_CREDIT = "MISSING_BANK_CREDIT"
SETTLEMENT_UNDER_CREDIT = "SETTLEMENT_UNDER_CREDIT"
DUPLICATE_REFUND = "DUPLICATE_REFUND"
UNVERIFIED_SETTLEMENT = "UNVERIFIED_SETTLEMENT"  # synthetic, only in failure mode

# ---------------------------------------------------------------------------
# Classification labels
# ---------------------------------------------------------------------------
EXPLAINED = "EXPLAINED"
EXCEPTION = "EXCEPTION"
NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"

# ---------------------------------------------------------------------------
# Deterministic confidence constants (Python sets these, never the LLM)
# ---------------------------------------------------------------------------
BASE_CONFIDENCE = {
    DUPLICATE_PAYMENT: 99,
    REFUND_EXCEEDS_PAYMENT: 96,
    MISSING_SETTLEMENT: 94,
    SETTLEMENT_UNDER_CREDIT: 93,
    MISSING_BANK_CREDIT: 90,
    DUPLICATE_REFUND: 88,
    STATUS_MISMATCH: 85,
    UNVERIFIED_SETTLEMENT: 50,
}

# Bonus added when all required evidence is present.
COMPLETENESS_BONUS = 2
# Penalty subtracted per detected conflict.
CONFLICT_PENALTY = 15
# When required evidence is missing, confidence is hard-capped here and the
# case is routed to NEEDS_HUMAN_REVIEW.
MISSING_EVIDENCE_CAP = 54

CONFIDENCE_MIN = 0
CONFIDENCE_MAX = 100

# ---------------------------------------------------------------------------
# Priority / severity
# ---------------------------------------------------------------------------
SEVERITY_WEIGHT = {
    DUPLICATE_PAYMENT: 1.5,
    MISSING_SETTLEMENT: 1.4,
    REFUND_EXCEEDS_PAYMENT: 1.3,
    SETTLEMENT_UNDER_CREDIT: 1.2,
    MISSING_BANK_CREDIT: 1.1,
    DUPLICATE_REFUND: 0.9,
    STATUS_MISMATCH: 0.8,
    UNVERIFIED_SETTLEMENT: 0.5,
}

# priority_score = amount_at_risk * (confidence/100) * age_factor * severity_weight
# Tier thresholds are applied to priority_score.
TIER_THRESHOLDS = {
    "CRITICAL": 8000,
    "HIGH": 3000,
    "MEDIUM": 800,
    "LOW": 0,
}

# ---------------------------------------------------------------------------
# AI investigation layer (provider-agnostic)
# ---------------------------------------------------------------------------
# Which AI provider generates investigations. One of:
#   "gemini" | "openai" | "claude" | "deterministic"
#   ("fallback" is accepted as an alias for "deterministic" — the dev/offline path)
# The financial engine is completely independent of this — switching providers
# is a configuration change only, no application code changes. The default is
# Gemini; Claude is NOT the default and is never required.
AI_PROVIDER = (os.environ.get("AI_PROVIDER") or "").strip().lower() or "gemini"

# Per-provider default models (override with the matching *_MODEL env var).
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
