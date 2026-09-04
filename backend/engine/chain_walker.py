"""Walk the six linked feeds into per-payment transaction chains.

Operates purely on list[dict] records (no pandas). Each chain links an
order -> payment -> refunds -> fees -> settlement -> bank_credit.
"""


def _index_by(records, key):
    out = {}
    for r in records:
        out.setdefault(r[key], []).append(r)
    return out


def _to_number(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return 0


NUMERIC_FIELDS = {"amount", "fee_amt", "tax_amt", "expected_amt", "actual_amt"}


def _coerce(record):
    """Return a copy with numeric string fields coerced to numbers."""
    out = dict(record)
    for k in list(out.keys()):
        if k in NUMERIC_FIELDS:
            out[k] = _to_number(out[k])
    return out


def build_chains(tables):
    """Given a dict of table-name -> list[dict], return a list of chain dicts.

    A chain is produced per payment (payments are the spine of the model).
    """
    orders = {o["order_id"]: _coerce(o) for o in tables.get("orders", [])}
    refunds_by_pay = _index_by([_coerce(r) for r in tables.get("refunds", [])], "payment_id")
    fees_by_pay = _index_by([_coerce(f) for f in tables.get("fees", [])], "payment_id")
    settle_by_pay = _index_by([_coerce(s) for s in tables.get("settlements", [])], "payment_id")
    credits_by_settle = _index_by([_coerce(c) for c in tables.get("bank_credits", [])], "settlement_id")

    # Count payments per order to support duplicate detection downstream.
    order_payment_ids = {}
    for p in tables.get("payments", []):
        order_payment_ids.setdefault(p["order_id"], []).append(p["payment_id"])

    chains = []
    for raw_pay in tables.get("payments", []):
        payment = _coerce(raw_pay)
        pid = payment["payment_id"]
        oid = payment["order_id"]
        settlements = settle_by_pay.get(pid, [])
        settlement = settlements[0] if settlements else None
        bank_credit = None
        if settlement is not None:
            creds = credits_by_settle.get(settlement["settlement_id"], [])
            bank_credit = creds[0] if creds else None
        chains.append({
            "payment_id": pid,
            "order_id": oid,
            "order": orders.get(oid),
            "payment": payment,
            "refunds": refunds_by_pay.get(pid, []),
            "fees": fees_by_pay.get(pid, []),
            "settlement": settlement,
            "bank_credit": bank_credit,
            "sibling_payment_ids": list(order_payment_ids.get(oid, [])),
        })
    return chains
