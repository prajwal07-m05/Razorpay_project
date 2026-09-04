"""Deterministic confidence, amount-at-risk, priority and tier. Pure Python.

The LLM never influences any number here.
"""

from datetime import datetime

from .. import config


def clamp(v, lo=config.CONFIDENCE_MIN, hi=config.CONFIDENCE_MAX):
    return max(lo, min(hi, v))


def compute_confidence(anomaly_type, evidence_complete, conflicts):
    """confidence = clamp(base + completeness - conflict_penalty).

    Missing required evidence hard-caps at MISSING_EVIDENCE_CAP.
    """
    if not evidence_complete:
        return config.MISSING_EVIDENCE_CAP
    base = config.BASE_CONFIDENCE.get(anomaly_type, 70)
    conf = base + config.COMPLETENESS_BONUS - config.CONFLICT_PENALTY * len(conflicts)
    return int(clamp(conf))


def compute_amount_at_risk(anomaly_type, derived):
    gross = derived["gross_payment"]
    refund_total = derived["refund_total"]
    gap = derived["unexplained_gap"]
    actual = derived["actual_settlement"]
    expected = derived["expected_settlement"]

    if anomaly_type == config.SETTLEMENT_UNDER_CREDIT:
        return abs(gap) if gap is not None else 0
    if anomaly_type == config.MISSING_SETTLEMENT:
        return abs(expected)
    if anomaly_type == config.MISSING_BANK_CREDIT:
        return abs(actual) if actual is not None else abs(expected)
    if anomaly_type == config.REFUND_EXCEEDS_PAYMENT:
        return abs(refund_total - gross)
    if anomaly_type == config.DUPLICATE_PAYMENT:
        return abs(gross)
    if anomaly_type == config.DUPLICATE_REFUND:
        # exposure = the duplicated (repeated) refund amount
        return abs(refund_total // 2) if refund_total else 0
    if anomaly_type == config.STATUS_MISMATCH:
        return abs(gross)
    if anomaly_type == config.UNVERIFIED_SETTLEMENT:
        return abs(actual) if actual is not None else abs(expected)
    return 0


def compute_age_hours(chain, now=None):
    now = now or datetime(2026, 9, 4, 12, 0, 0)
    ts = chain["payment"].get("ts")
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return 0.0
    delta = now - dt
    return round(delta.total_seconds() / 3600.0, 2)


def _age_factor(age_hours):
    # Older items are slightly more urgent; bounded so amount dominates.
    return min(2.0, 1.0 + age_hours / 720.0)


def compute_priority(anomaly_type, amount_at_risk, confidence, age_hours):
    severity = config.SEVERITY_WEIGHT.get(anomaly_type, 1.0)
    score = amount_at_risk * (confidence / 100.0) * _age_factor(age_hours) * severity
    return round(score, 2)


def tier_for(priority_score):
    if priority_score >= config.TIER_THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    if priority_score >= config.TIER_THRESHOLDS["HIGH"]:
        return "HIGH"
    if priority_score >= config.TIER_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"
