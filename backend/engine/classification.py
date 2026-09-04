"""Chain / case classification. Pure Python."""

from .. import config


def classify_chain(anomalies, evidence_complete, conflicts, derived):
    """Chain-level classification (before per-anomaly case creation).

    EXPLAINED           -> no anomalies and expected==actual==bank_credit
    CONFLICTING_EVIDENCE-> contradictory recorded states
    NEEDS_HUMAN_REVIEW  -> required verification evidence missing
    EXCEPTION           -> a real unexplained anomaly with complete evidence
    """
    if not anomalies:
        expected = derived["expected_settlement"]
        actual = derived["actual_settlement"]
        bank = derived["bank_credit_amount"]
        if actual is not None and bank is not None and expected == actual == bank:
            return config.EXPLAINED
        if actual is None and bank is None:
            # payment not settled / nothing to reconcile
            return config.EXPLAINED
        return config.EXPLAINED

    if conflicts:
        return config.CONFLICTING_EVIDENCE
    if not evidence_complete:
        return config.NEEDS_HUMAN_REVIEW
    return config.EXCEPTION


def classify_case(anomaly_type, evidence_complete, conflicts):
    """Per-case classification for a single detected anomaly."""
    if conflicts and anomaly_type == config.STATUS_MISMATCH:
        return config.CONFLICTING_EVIDENCE
    if not evidence_complete:
        return config.NEEDS_HUMAN_REVIEW
    if conflicts:
        return config.CONFLICTING_EVIDENCE
    return config.EXCEPTION
