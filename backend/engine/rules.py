"""Anomaly detection rules. Pure Python; operate on chains + derived values."""

from .. import config


def find_duplicate_payment_ids(chains):
    """Return the set of payment_ids that are duplicates.

    Two+ payments for the same order with the same amount => every payment
    after the first (by sorted payment_id) is a duplicate.
    """
    by_order = {}
    for ch in chains:
        by_order.setdefault(ch["order_id"], []).append(ch["payment"])

    dupes = set()
    for oid, pays in by_order.items():
        by_amount = {}
        for p in pays:
            by_amount.setdefault(p.get("amount"), []).append(p["payment_id"])
        for amount, pids in by_amount.items():
            if len(pids) > 1:
                for extra in sorted(pids)[1:]:
                    dupes.add(extra)
    return dupes


def _settled(payment):
    return payment.get("status") in ("settled", "completed")


def detect_anomalies(chain, derived, duplicate_ids, bank_feed_available):
    """Return an ordered list of anomaly-type strings for one chain."""
    anomalies = []
    order = chain["order"]
    payment = chain["payment"]
    settlement = chain["settlement"]
    bank = chain["bank_credit"]
    pid = payment["payment_id"]

    if pid in duplicate_ids:
        anomalies.append(config.DUPLICATE_PAYMENT)

    if derived["refund_total"] > derived["gross_payment"]:
        anomalies.append(config.REFUND_EXCEEDS_PAYMENT)

    # Duplicate refund: two+ refunds sharing the same amount.
    refund_amts = [r.get("amount") for r in chain["refunds"]]
    if len(refund_amts) > 1 and len(set(refund_amts)) < len(refund_amts):
        anomalies.append(config.DUPLICATE_REFUND)

    if order is not None and order.get("status") == "cancelled" and _settled(payment):
        anomalies.append(config.STATUS_MISMATCH)

    if _settled(payment):
        if settlement is None:
            anomalies.append(config.MISSING_SETTLEMENT)
        else:
            # A genuine single missing bank credit is only detectable while the
            # feed is healthy. When the feed is down (failure mode) we cannot
            # distinguish, so we do not raise MISSING_BANK_CREDIT then.
            if bank_feed_available and bank is None:
                anomalies.append(config.MISSING_BANK_CREDIT)
            # SETTLEMENT_UNDER_CREDIT is an INTERNAL discrepancy (expected vs
            # actual lives in the settlements table) so it fires regardless of
            # the bank feed. When the feed is offline the loss cannot be
            # confirmed, which is handled downstream as incomplete evidence.
            if derived["unexplained_gap"] not in (None, 0):
                anomalies.append(config.SETTLEMENT_UNDER_CREDIT)

    return anomalies
