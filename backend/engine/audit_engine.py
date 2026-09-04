"""Orchestrates the audit: chains -> rules -> evidence -> scoring -> cases.

Pure Python; consumes a dict of table records (see chain_walker). The FastAPI
layer supplies records via loader.py (the only pandas module); tests supply
records loaded with the stdlib csv module.
"""

from .. import config
from . import chain_walker, classification, evidence, failure_sim, rules

TITLES = {
    config.MISSING_SETTLEMENT: "Missing settlement for settled payment",
    config.DUPLICATE_PAYMENT: "Duplicate payment for order",
    config.REFUND_EXCEEDS_PAYMENT: "Refund exceeds original payment",
    config.STATUS_MISMATCH: "Order/payment status mismatch",
    config.MISSING_BANK_CREDIT: "Settlement recorded but no bank credit",
    config.SETTLEMENT_UNDER_CREDIT: "Settlement under-credited vs expected",
    config.DUPLICATE_REFUND: "Duplicate refund issued",
    config.UNVERIFIED_SETTLEMENT: "Settled record cannot be verified (feed down)",
}


def _build_case(case_id, chain, derived, anomaly_type, packet, missing, conflicts, complete):
    from . import scoring
    confidence = scoring.compute_confidence(anomaly_type, complete, conflicts)
    amount_at_risk = scoring.compute_amount_at_risk(anomaly_type, derived)
    age_hours = scoring.compute_age_hours(chain)
    priority_score = scoring.compute_priority(anomaly_type, amount_at_risk, confidence, age_hours)
    tier = scoring.tier_for(priority_score)
    case_class = classification.classify_case(anomaly_type, complete, conflicts)

    return {
        "case_id": case_id,
        "payment_id": chain["payment_id"],
        "order_id": chain["order_id"],
        "type": anomaly_type,
        "title": TITLES.get(anomaly_type, anomaly_type),
        "classification": case_class,
        "amount_at_risk": amount_at_risk,
        "base_confidence": config.BASE_CONFIDENCE.get(anomaly_type, 70),
        "confidence": confidence,
        "age_hours": age_hours,
        "priority_score": priority_score,
        "tier": tier,
        "method": chain["payment"].get("method"),
        "evidence_packet": packet,
        "evidence_items": evidence.build_evidence_items(chain, derived, [anomaly_type]),
        "chain": evidence.build_chain_view(chain, derived, [anomaly_type]),
        "investigation": None,
    }


def run_audit(tables, mode="normal"):
    """Run the full audit. Returns {mode, summary, cases}."""
    run_tables, bank_feed_available = failure_sim.apply_mode(tables, mode)
    chains = chain_walker.build_chains(run_tables)
    duplicate_ids = rules.find_duplicate_payment_ids(chains)

    cases = []
    explained = 0
    exceptions = 0
    needs_review = 0
    case_seq = 0

    for chain in chains:
        derived = evidence.derive_values(chain)
        base_missing, conflicts, base_complete = evidence.assess_evidence(chain)
        anomalies = rules.detect_anomalies(chain, derived, duplicate_ids, bank_feed_available)

        if not anomalies:
            # A balanced settlement stays EXPLAINED even when the bank feed is
            # offline; the offline feed is a run-level caveat, not a case.
            chain_class = classification.classify_chain(anomalies, base_complete, conflicts, derived)
            if chain_class == config.EXPLAINED:
                explained += 1
            continue

        for anomaly_type in anomalies:
            missing, complete = evidence.finalize_case_evidence(
                anomaly_type, base_missing, base_complete, bank_feed_available)
            case_seq += 1
            case_id = "CASE-%04d" % case_seq
            packet = evidence.build_evidence_packet(
                case_id, chain, derived, missing, conflicts, complete)
            case = _build_case(case_id, chain, derived, anomaly_type, packet,
                               missing, conflicts, complete)
            if case["classification"] == config.NEEDS_HUMAN_REVIEW:
                needs_review += 1
            else:
                exceptions += 1
            cases.append(case)

    cases.sort(key=lambda c: c["priority_score"], reverse=True)

    potential_exposure = sum(c["amount_at_risk"] for c in cases)
    summary = {
        "records_processed": len(chains),
        "reconciled": explained,
        "explained": explained,
        "exceptions": exceptions,
        "needs_review": needs_review,
        "potential_exposure": potential_exposure,
        "bank_feed_available": bank_feed_available,
    }
    return {"mode": mode, "summary": summary, "cases": cases}
