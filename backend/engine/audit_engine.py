"""Deterministic CaseFile audit engine.

The production path streams transaction chains one at a time. It keeps only
the final exception cases rather than materializing all 100K chains.
"""

from .. import config
from . import (
    chain_walker,
    classification,
    evidence,
    failure_sim,
    rules,
)


TITLES = {
    config.MISSING_SETTLEMENT:
        "Missing settlement for settled payment",

    config.DUPLICATE_PAYMENT:
        "Duplicate payment for order",

    config.REFUND_EXCEEDS_PAYMENT:
        "Refund exceeds original payment",

    config.STATUS_MISMATCH:
        "Order/payment status mismatch",

    config.MISSING_BANK_CREDIT:
        "Settlement recorded but no bank credit",

    config.SETTLEMENT_UNDER_CREDIT:
        "Settlement under-credited vs expected",

    config.DUPLICATE_REFUND:
        "Duplicate refund issued",

    config.UNVERIFIED_SETTLEMENT:
        "Settled record cannot be verified (feed down)",
}


def _build_case(
    case_id,
    chain,
    derived,
    anomaly_type,
    packet,
    missing,
    conflicts,
    complete,
):
    from . import scoring

    confidence = scoring.compute_confidence(
        anomaly_type,
        complete,
        conflicts,
    )

    amount_at_risk = scoring.compute_amount_at_risk(
        anomaly_type,
        derived,
    )

    age_hours = scoring.compute_age_hours(chain)

    priority_score = scoring.compute_priority(
        anomaly_type,
        amount_at_risk,
        confidence,
        age_hours,
    )

    tier = scoring.tier_for(priority_score)

    case_class = classification.classify_case(
        anomaly_type,
        complete,
        conflicts,
    )

    return {
        "case_id": case_id,
        "payment_id": chain["payment_id"],
        "order_id": chain["order_id"],
        "type": anomaly_type,
        "title": TITLES.get(
            anomaly_type,
            anomaly_type,
        ),
        "classification": case_class,
        "amount_at_risk": amount_at_risk,
        "base_confidence": config.BASE_CONFIDENCE.get(
            anomaly_type,
            70,
        ),
        "confidence": confidence,
        "age_hours": age_hours,
        "priority_score": priority_score,
        "tier": tier,
        "method": chain["payment"].get("method"),
        "evidence_packet": packet,
        "evidence_items": evidence.build_evidence_items(
            chain,
            derived,
            [anomaly_type],
        ),
        "chain": evidence.build_chain_view(
            chain,
            derived,
            [anomaly_type],
        ),
        "investigation": None,
    }


def run_audit(tables, mode="normal"):
    """Run the deterministic audit.

    Important memory property:
    - no 100K chain list
    - only the final exception cases are retained
    - numeric truth remains entirely deterministic
    """

    run_tables, bank_feed_available = failure_sim.apply_mode(
        tables,
        mode,
    )

    duplicate_ids = rules.find_duplicate_payment_ids_from_tables(
        run_tables
    )

    cases = []

    explained = 0
    exceptions = 0
    needs_review = 0

    case_seq = 0
    records_processed = 0

    for chain in chain_walker.iter_chains(run_tables):
        records_processed += 1

        derived = evidence.derive_values(chain)

        (
            base_missing,
            conflicts,
            base_complete,
        ) = evidence.assess_evidence(chain)

        anomalies = rules.detect_anomalies(
            chain,
            derived,
            duplicate_ids,
            bank_feed_available,
        )

        if not anomalies:
            chain_class = classification.classify_chain(
                anomalies,
                base_complete,
                conflicts,
                derived,
            )

            if chain_class == config.EXPLAINED:
                explained += 1

            continue

        for anomaly_type in anomalies:
            (
                missing,
                complete,
            ) = evidence.finalize_case_evidence(
                anomaly_type,
                base_missing,
                base_complete,
                bank_feed_available,
            )

            case_seq += 1

            case_id = "CASE-%04d" % case_seq

            packet = evidence.build_evidence_packet(
                case_id,
                chain,
                derived,
                missing,
                conflicts,
                complete,
            )

            case = _build_case(
                case_id,
                chain,
                derived,
                anomaly_type,
                packet,
                missing,
                conflicts,
                complete,
            )

            if case["classification"] == config.NEEDS_HUMAN_REVIEW:
                needs_review += 1
            else:
                exceptions += 1

            cases.append(case)

    cases.sort(
        key=lambda case: case["priority_score"],
        reverse=True,
    )

    potential_exposure = sum(
        case["amount_at_risk"]
        for case in cases
    )

    summary = {
        "records_processed": records_processed,
        "reconciled": explained,
        "explained": explained,
        "exceptions": exceptions,
        "needs_review": needs_review,
        "potential_exposure": potential_exposure,
        "bank_feed_available": bank_feed_available,
    }

    return {
        "mode": mode,
        "summary": summary,
        "cases": cases,
    }
