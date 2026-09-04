"""Derive authoritative financial values and assemble evidence packets.

All arithmetic lives here (and in scoring). The LLM never computes numbers.
Pure Python; no pandas.
"""


def derive_values(chain):
    """Compute the authoritative per-payment financial values."""
    payment = chain["payment"]
    gross_payment = payment.get("amount", 0)
    refund_total = sum(r.get("amount", 0) for r in chain["refunds"])
    fee_total = sum(f.get("fee_amt", 0) + f.get("tax_amt", 0) for f in chain["fees"])
    expected_settlement = gross_payment - refund_total - fee_total

    settlement = chain["settlement"]
    if settlement is not None:
        actual_settlement = settlement.get("actual_amt", 0)
    else:
        actual_settlement = None

    bank_credit = chain["bank_credit"]
    bank_credit_amount = bank_credit.get("amount") if bank_credit is not None else None

    if actual_settlement is None:
        unexplained_gap = None
    else:
        unexplained_gap = expected_settlement - actual_settlement

    return {
        "gross_payment": gross_payment,
        "refund_total": refund_total,
        "fee_total": fee_total,
        "expected_settlement": expected_settlement,
        "actual_settlement": actual_settlement,
        "bank_credit_amount": bank_credit_amount,
        "unexplained_gap": unexplained_gap,
    }


def _settled(payment):
    return payment.get("status") in ("settled", "completed")


def assess_evidence(chain):
    """Return (missing_evidence, conflicts, evidence_complete) for a chain.

    This is the feed-independent base assessment: it only reflects genuinely
    absent core records and contradictory recorded states. The bank-credit
    feed being offline is applied per-case (see finalize_case_evidence),
    because it only undermines findings that depend on the bank feed to
    CONFIRM a loss.
    """
    payment = chain["payment"]
    order = chain["order"]

    missing = []
    conflicts = []
    complete = True

    if order is None:
        missing.append("order")
        complete = False

    # Contradictory recorded states.
    if order is not None and order.get("status") == "cancelled" and _settled(payment):
        conflicts.append("order_cancelled_but_payment_settled")

    return missing, conflicts, complete


# Findings whose confirmation depends on observing the bank-credit feed. When
# the feed is offline these cannot be confirmed, so their evidence is
# incomplete. Feed-independent anomalies (duplicate payment, missing
# settlement, refund exceeds, status mismatch) are unaffected.
def finalize_case_evidence(anomaly_type, base_missing, base_complete, bank_feed_available):
    from .. import config as _c
    bank_dependent = anomaly_type == _c.SETTLEMENT_UNDER_CREDIT
    missing = list(base_missing)
    complete = base_complete
    if bank_dependent and not bank_feed_available:
        missing.append("bank_credit_feed")
        complete = False
    return missing, complete


def build_evidence_packet(case_id, chain, derived, missing, conflicts, complete):
    return {
        "case_id": case_id,
        "order": chain["order"],
        "payment": chain["payment"],
        "refunds": chain["refunds"],
        "fees": chain["fees"],
        "settlement": chain["settlement"],
        "bank_credit": chain["bank_credit"],
        "derived_values": {
            "gross_payment": derived["gross_payment"],
            "refund_total": derived["refund_total"],
            "fee_total": derived["fee_total"],
            "expected_settlement": derived["expected_settlement"],
            "actual_settlement": derived["actual_settlement"],
            "bank_credit_amount": derived["bank_credit_amount"],
            "unexplained_gap": derived["unexplained_gap"],
        },
        "conflicts": conflicts,
        "missing_evidence": missing,
        "evidence_complete": complete,
    }


def build_evidence_items(chain, derived, anomalies):
    """Flat evidence list for the UI. status in ok|broken|missing."""
    items = []
    order = chain["order"]
    payment = chain["payment"]

    order_status = "ok"
    from .. import config as _c  # local import to avoid cycles at module load
    if _c.STATUS_MISMATCH in anomalies:
        order_status = "broken"
    items.append({
        "source": "orders",
        "label": "Order",
        "value": order.get("amount") if order else None,
        "status": order_status if order else "missing",
    })

    pay_status = "broken" if _c.DUPLICATE_PAYMENT in anomalies else "ok"
    items.append({
        "source": "payments",
        "label": "Payment (gross)",
        "value": derived["gross_payment"],
        "status": pay_status,
    })

    refund_status = "ok" if chain["refunds"] else "missing"
    if _c.REFUND_EXCEEDS_PAYMENT in anomalies or _c.DUPLICATE_REFUND in anomalies:
        refund_status = "broken"
    items.append({
        "source": "refunds",
        "label": "Refund total",
        "value": derived["refund_total"],
        "status": refund_status,
    })

    items.append({
        "source": "fees",
        "label": "Fee + tax total",
        "value": derived["fee_total"],
        "status": "ok" if chain["fees"] else "missing",
    })

    if chain["settlement"] is None:
        set_status = "missing"
    elif _c.SETTLEMENT_UNDER_CREDIT in anomalies:
        set_status = "broken"
    else:
        set_status = "ok"
    items.append({
        "source": "settlements",
        "label": "Actual settlement",
        "value": derived["actual_settlement"],
        "status": set_status,
    })

    if chain["bank_credit"] is None:
        bank_status = "missing"
    else:
        bank_status = "ok"
    items.append({
        "source": "bank_credits",
        "label": "Bank credit",
        "value": derived["bank_credit_amount"],
        "status": bank_status,
    })
    return items


def build_chain_view(chain, derived, anomalies):
    """Ordered chain for the UI, highlighting the broken link."""
    from .. import config as _c
    order = chain["order"]
    payment = chain["payment"]
    settlement = chain["settlement"]
    bank = chain["bank_credit"]

    view = []
    view.append({
        "stage": "ORDER",
        "id": order["order_id"] if order else None,
        "label": "Order",
        "value": order.get("amount") if order else None,
        "status": "broken" if _c.STATUS_MISMATCH in anomalies else ("ok" if order else "missing"),
    })
    view.append({
        "stage": "PAYMENT",
        "id": payment["payment_id"],
        "label": "Payment",
        "value": derived["gross_payment"],
        "status": "broken" if _c.DUPLICATE_PAYMENT in anomalies else "ok",
    })
    view.append({
        "stage": "REFUND",
        "id": chain["refunds"][0]["refund_id"] if chain["refunds"] else None,
        "label": "Refunds",
        "value": derived["refund_total"],
        "status": ("broken" if (_c.REFUND_EXCEEDS_PAYMENT in anomalies or _c.DUPLICATE_REFUND in anomalies)
                   else ("ok" if chain["refunds"] else "missing")),
    })
    view.append({
        "stage": "FEE",
        "id": chain["fees"][0]["fee_id"] if chain["fees"] else None,
        "label": "Fees",
        "value": derived["fee_total"],
        "status": "ok" if chain["fees"] else "missing",
    })
    view.append({
        "stage": "SETTLEMENT",
        "id": settlement["settlement_id"] if settlement else None,
        "label": "Settlement",
        "value": derived["actual_settlement"],
        "status": ("missing" if settlement is None
                   else ("broken" if _c.SETTLEMENT_UNDER_CREDIT in anomalies else "ok")),
    })
    view.append({
        "stage": "BANK_CREDIT",
        "id": bank["credit_id"] if bank else None,
        "label": "Bank credit",
        "value": derived["bank_credit_amount"],
        "status": ("missing" if bank is None
                   else ("broken" if _c.SETTLEMENT_UNDER_CREDIT in anomalies else "ok")),
    })
    return view
