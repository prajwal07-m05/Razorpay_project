"""Anomaly detection rules.

Pure Python. No LLM and no pandas.
"""

from .. import config


def find_duplicate_payment_ids(chains):
    """Return duplicate payment IDs from already-built chains.

    Compatibility path for tests and small datasets.
    """

    by_order = {}

    for chain in chains:
        by_order.setdefault(
            chain["order_id"],
            [],
        ).append(chain["payment"])

    dupes = set()

    for _order_id, payments in by_order.items():
        by_amount = {}

        for payment in payments:
            by_amount.setdefault(
                payment.get("amount"),
                [],
            ).append(payment["payment_id"])

        for _amount, payment_ids in by_amount.items():
            if len(payment_ids) > 1:
                for extra in sorted(payment_ids)[1:]:
                    dupes.add(extra)

    return dupes


def find_duplicate_payment_ids_from_tables(tables):
    """Find duplicate payments without first constructing 100K chains."""

    groups = {}

    for payment in tables.get("payments", []):
        key = (
            payment["order_id"],
            payment.get("amount"),
        )

        groups.setdefault(
            key,
            [],
        ).append(payment["payment_id"])

    duplicates = set()

    for payment_ids in groups.values():
        if len(payment_ids) > 1:
            duplicates.update(
                sorted(payment_ids)[1:]
            )

    return duplicates


def _settled(payment):
    return payment.get("status") in (
        "settled",
        "completed",
    )


def detect_anomalies(
    chain,
    derived,
    duplicate_ids,
    bank_feed_available,
):
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

    refund_amts = [
        refund.get("amount")
        for refund in chain["refunds"]
    ]

    if (
        len(refund_amts) > 1
        and len(set(refund_amts)) < len(refund_amts)
    ):
        anomalies.append(config.DUPLICATE_REFUND)

    if (
        order is not None
        and order.get("status") == "cancelled"
        and _settled(payment)
    ):
        anomalies.append(config.STATUS_MISMATCH)

    if _settled(payment):
        if settlement is None:
            anomalies.append(config.MISSING_SETTLEMENT)
        else:
            if bank_feed_available and bank is None:
                anomalies.append(config.MISSING_BANK_CREDIT)

            if derived["unexplained_gap"] not in (
                None,
                0,
            ):
                anomalies.append(
                    config.SETTLEMENT_UNDER_CREDIT
                )

    return anomalies
