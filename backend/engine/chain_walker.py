"""Walk the six linked feeds into per-payment transaction chains.

The audit path uses iter_chains(), which streams one chain at a time instead
of retaining 100K chain dictionaries in memory.

build_chains() remains available for tests and compatibility.
"""

def _index_by(records, key):
    out = {}

    for record in records:
        out.setdefault(record[key], []).append(record)

    return out


def _to_number(value):
    if value is None or value == "":
        return 0

    if isinstance(value, (int, float)):
        return value

    value = str(value).strip()

    try:
        if "." in value:
            return float(value)

        return int(value)

    except ValueError:
        return 0


NUMERIC_FIELDS = {
    "amount",
    "fee_amt",
    "tax_amt",
    "expected_amt",
    "actual_amt",
}


def _coerce(record):
    """Return a copy with numeric string fields coerced to numbers."""
    out = dict(record)

    for key in list(out.keys()):
        if key in NUMERIC_FIELDS:
            out[key] = _to_number(out[key])

    return out


def _build_indexes(tables):
    """Build lookup indexes without constructing transaction chains."""

    orders = {
        order["order_id"]: order
        for order in tables.get("orders", [])
    }

    refunds_by_pay = _index_by(
        tables.get("refunds", []),
        "payment_id",
    )

    fees_by_pay = _index_by(
        tables.get("fees", []),
        "payment_id",
    )

    settle_by_pay = _index_by(
        tables.get("settlements", []),
        "payment_id",
    )

    credits_by_settle = _index_by(
        tables.get("bank_credits", []),
        "settlement_id",
    )

    order_payment_ids = {}

    for payment in tables.get("payments", []):
        order_payment_ids.setdefault(
            payment["order_id"],
            [],
        ).append(payment["payment_id"])

    return (
        orders,
        refunds_by_pay,
        fees_by_pay,
        settle_by_pay,
        credits_by_settle,
        order_payment_ids,
    )


def iter_chains(tables):
    """Yield one transaction chain at a time.

    This is the production path. It avoids creating a 100K-element list of
    chain dictionaries before the audit can start processing.
    """

    (
        orders,
        refunds_by_pay,
        fees_by_pay,
        settle_by_pay,
        credits_by_settle,
        _order_payment_ids,
    ) = _build_indexes(tables)

    for raw_payment in tables.get("payments", []):
        payment = raw_payment

        pid = payment["payment_id"]
        oid = payment["order_id"]

        settlements = settle_by_pay.get(pid, [])
        settlement = settlements[0] if settlements else None

        bank_credit = None

        if settlement is not None:
            credits = credits_by_settle.get(
                settlement["settlement_id"],
                [],
            )

            bank_credit = credits[0] if credits else None

        yield {
            "payment_id": pid,
            "order_id": oid,
            "order": orders.get(oid),
            "payment": payment,
            "refunds": refunds_by_pay.get(pid, []),
            "fees": fees_by_pay.get(pid, []),
            "settlement": settlement,
            "bank_credit": bank_credit,
            "sibling_payment_ids": None,
        }


def build_chains(tables):
    """Compatibility helper used by tests and small datasets."""

    orders = {
        order["order_id"]: _coerce(order)
        for order in tables.get("orders", [])
    }

    refunds_by_pay = _index_by(
        [_coerce(r) for r in tables.get("refunds", [])],
        "payment_id",
    )

    fees_by_pay = _index_by(
        [_coerce(f) for f in tables.get("fees", [])],
        "payment_id",
    )

    settle_by_pay = _index_by(
        [_coerce(s) for s in tables.get("settlements", [])],
        "payment_id",
    )

    credits_by_settle = _index_by(
        [_coerce(c) for c in tables.get("bank_credits", [])],
        "settlement_id",
    )

    order_payment_ids = {}

    for payment in tables.get("payments", []):
        order_payment_ids.setdefault(
            payment["order_id"],
            [],
        ).append(payment["payment_id"])

    chains = []

    for raw_pay in tables.get("payments", []):
        payment = _coerce(raw_pay)

        pid = payment["payment_id"]
        oid = payment["order_id"]

        settlements = settle_by_pay.get(pid, [])
        settlement = settlements[0] if settlements else None

        bank_credit = None

        if settlement is not None:
            credits = credits_by_settle.get(
                settlement["settlement_id"],
                [],
            )

            bank_credit = credits[0] if credits else None

        chains.append({
            "payment_id": pid,
            "order_id": oid,
            "order": orders.get(oid),
            "payment": payment,
            "refunds": refunds_by_pay.get(pid, []),
            "fees": fees_by_pay.get(pid, []),
            "settlement": settlement,
            "bank_credit": bank_credit,
            "sibling_payment_ids": list(
                order_payment_ids.get(oid, [])
            ),
        })

    return chains
