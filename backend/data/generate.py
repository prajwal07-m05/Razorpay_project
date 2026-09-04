"""Deterministic, scalable generator for the CaseFile linked financial dataset.

Generates N *canonical* financial transactions. Each canonical transaction is
built first and its related records (order, payment, refunds, fee, settlement,
bank credit) are DERIVED from it, so the relationships are internally
consistent — this is not N independent rows per table.

Reproducible: the same --records and --seed always produce the same dataset
(seeded RNG, deterministic iteration). The engine must NEVER read
ground_truth.json; it exists solely so the metrics endpoint can score the
engine's precision / recall AFTER a run.

Run:
    python -m backend.data.generate --records 100000 --seed 42
    CASEFILE_DATASET_SIZE=100000 CASEFILE_SEED=42 python -m backend.data.generate
"""
import argparse
import csv
import json
import os
import random
import time
from datetime import datetime, timedelta

from .. import config

NOW = datetime(2026, 9, 4, 12, 0, 0)
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Fee model (integer rupees throughout to keep arithmetic exact and testable;
# whole-rupee precision is the appropriate monetary granularity here).
FEE_RATE = 0.02
TAX_RATE = 0.005

# The seven anomaly families the injector can plant into the bulk population.
INJECTABLE = [
    config.SETTLEMENT_UNDER_CREDIT,
    config.MISSING_SETTLEMENT,
    config.MISSING_BANK_CREDIT,
    config.DUPLICATE_PAYMENT,
    config.REFUND_EXCEEDS_PAYMENT,
    config.STATUS_MISMATCH,
    config.DUPLICATE_REFUND,
]


def _fees_for(amount):
    return round(amount * FEE_RATE), round(amount * TAX_RATE)


class Builder:
    """Accumulates the six linked tables plus hidden ground truth."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.orders = []
        self.payments = []
        self.refunds = []
        self.fees = []
        self.settlements = []
        self.bank_credits = []
        self.ground_truth = []
        self._pay = self._ref = self._fee = self._set = self._cr = 0

    # -- id helpers ------------------------------------------------------
    def next_pay(self):
        self._pay += 1
        return "PAY%06d" % self._pay

    def next_ref(self):
        self._ref += 1
        return "REF%06d" % self._ref

    def next_fee(self):
        self._fee += 1
        return "FEE%06d" % self._fee

    def next_set(self):
        self._set += 1
        return "SET%06d" % self._set

    def next_cr(self):
        self._cr += 1
        return "CR%06d" % self._cr

    def ts(self, age_hours):
        return (NOW - timedelta(hours=age_hours)).isoformat()

    # -- record builders -------------------------------------------------
    def add_order(self, order_id, amount, status="completed"):
        self.orders.append({"order_id": order_id, "amount": amount, "status": status})

    def add_payment(self, order_id, amount, status="settled", method="card", age=24):
        pid = self.next_pay()
        self.payments.append({
            "payment_id": pid, "order_id": order_id, "amount": amount,
            "status": status, "method": method, "ts": self.ts(age),
        })
        return pid

    def add_refund(self, payment_id, amount, age=12):
        rid = self.next_ref()
        self.refunds.append({
            "refund_id": rid, "payment_id": payment_id, "amount": amount, "ts": self.ts(age),
        })
        return rid

    def add_fee(self, payment_id, fee_amt, tax_amt):
        fid = self.next_fee()
        self.fees.append({
            "fee_id": fid, "payment_id": payment_id, "fee_amt": fee_amt, "tax_amt": tax_amt,
        })
        return fid

    def add_settlement(self, payment_id, expected_amt, actual_amt, status="settled", age=6):
        sid = self.next_set()
        self.settlements.append({
            "settlement_id": sid, "payment_id": payment_id, "expected_amt": expected_amt,
            "actual_amt": actual_amt, "status": status, "ts": self.ts(age),
        })
        return sid

    def add_bank_credit(self, settlement_id, amount, age=3):
        cid = self.next_cr()
        self.bank_credits.append({
            "credit_id": cid, "settlement_id": settlement_id, "amount": amount, "ts": self.ts(age),
        })
        return cid

    def gt(self, payment_id, type_):
        self.ground_truth.append({"payment_id": payment_id, "type": type_})

    # -- composite: a fully reconciled ("explained") chain ---------------
    def clean_chain(self, order_id, amount, refund=0, method="card", age=None):
        if age is None:
            age = self.rng.randint(3, 700)
        self.add_order(order_id, amount, "completed")
        pid = self.add_payment(order_id, amount, "settled", method, age)
        if refund:
            self.add_refund(pid, refund, max(1, age - 1))
        fee_amt, tax_amt = _fees_for(amount)
        self.add_fee(pid, fee_amt, tax_amt)
        expected = amount - refund - (fee_amt + tax_amt)
        sid = self.add_settlement(pid, expected, expected, "settled", max(1, age - 4))
        self.add_bank_credit(sid, expected, max(1, age - 5))
        return pid

    # -- composite: a bulk-injected anomaly ------------------------------
    def inject(self, order_id, anomaly_type, method):
        """Actually modify the linked records so the engine has to discover it.

        Amounts are kept modest so the hand-curated hero cases stay near the
        top of the priority ranking.
        """
        amount = self.rng.randint(1000, 15000)
        age = self.rng.randint(3, 500)
        fee_amt, tax_amt = _fees_for(amount)
        fee_total = fee_amt + tax_amt

        if anomaly_type == config.SETTLEMENT_UNDER_CREDIT:
            self.add_order(order_id, amount, "completed")
            pid = self.add_payment(order_id, amount, "settled", method, age)
            self.add_fee(pid, fee_amt, tax_amt)
            expected = amount - fee_total
            gap = self.rng.randint(200, max(300, amount // 6))
            sid = self.add_settlement(pid, expected, expected - gap, "settled", max(1, age - 4))
            self.add_bank_credit(sid, expected - gap, max(1, age - 5))
            self.gt(pid, anomaly_type)

        elif anomaly_type == config.MISSING_SETTLEMENT:
            self.add_order(order_id, amount, "completed")
            pid = self.add_payment(order_id, amount, "settled", method, age)
            self.add_fee(pid, fee_amt, tax_amt)
            # No settlement, no bank credit.
            self.gt(pid, anomaly_type)

        elif anomaly_type == config.MISSING_BANK_CREDIT:
            self.add_order(order_id, amount, "completed")
            pid = self.add_payment(order_id, amount, "settled", method, age)
            self.add_fee(pid, fee_amt, tax_amt)
            expected = amount - fee_total
            self.add_settlement(pid, expected, expected, "settled", max(1, age - 4))
            # No bank credit row.
            self.gt(pid, anomaly_type)

        elif anomaly_type == config.DUPLICATE_PAYMENT:
            self.add_order(order_id, amount, "completed")
            for _ in range(2):
                pid = self.add_payment(order_id, amount, "settled", method, age)
                self.add_fee(pid, fee_amt, tax_amt)
                expected = amount - fee_total
                sid = self.add_settlement(pid, expected, expected, "settled", max(1, age - 4))
                self.add_bank_credit(sid, expected, max(1, age - 5))
            self.gt(pid, anomaly_type)  # second payment is the duplicate

        elif anomaly_type == config.REFUND_EXCEEDS_PAYMENT:
            self.add_order(order_id, amount, "completed")
            pid = self.add_payment(order_id, amount, "settled", method, age)
            over = amount + self.rng.randint(200, 2000)
            self.add_refund(pid, over, max(1, age - 1))
            expected = amount - over
            sid = self.add_settlement(pid, expected, expected, "settled", max(1, age - 4))
            self.add_bank_credit(sid, expected, max(1, age - 5))
            self.gt(pid, anomaly_type)

        elif anomaly_type == config.STATUS_MISMATCH:
            self.add_order(order_id, amount, "cancelled")
            pid = self.add_payment(order_id, amount, "settled", method, age)
            self.add_fee(pid, fee_amt, tax_amt)
            expected = amount - fee_total
            sid = self.add_settlement(pid, expected, expected, "settled", max(1, age - 4))
            self.add_bank_credit(sid, expected, max(1, age - 5))
            self.gt(pid, anomaly_type)

        elif anomaly_type == config.DUPLICATE_REFUND:
            self.add_order(order_id, amount, "completed")
            pid = self.add_payment(order_id, amount, "settled", method, age)
            self.add_fee(pid, fee_amt, tax_amt)
            dup = self.rng.randint(100, amount // 6)
            self.add_refund(pid, dup, max(1, age - 1))
            self.add_refund(pid, dup, max(1, age - 2))  # identical amount => duplicate
            expected = amount - 2 * dup - fee_total
            sid = self.add_settlement(pid, expected, expected, "settled", max(1, age - 4))
            self.add_bank_credit(sid, expected, max(1, age - 5))
            self.gt(pid, anomaly_type)

    def tables(self):
        return {
            "orders": self.orders,
            "payments": self.payments,
            "refunds": self.refunds,
            "fees": self.fees,
            "settlements": self.settlements,
            "bank_credits": self.bank_credits,
        }

    def total_records(self):
        t = self.tables()
        return sum(len(v) for v in t.values())


# The 15 hand-curated planted anomalies (orders O000001 .. O000015), including
# the HERO case (index 1) with the exact spec values. These anchor the demo and
# the tests, and stay near the top of the priority ranking.
def _add_curated(b):
    # 1) HERO: SETTLEMENT_UNDER_CREDIT with exact spec values.
    b.add_order("O000001", 20000, "completed")
    pid = b.add_payment("O000001", 20000, "settled", "card", 30)
    b.add_refund(pid, 1000, 20)
    b.add_fee(pid, 500, 80)  # fee_total 580
    sid = b.add_settlement(pid, 18420, 16420, "settled", 8)
    b.add_bank_credit(sid, 16420, 5)
    b.gt(pid, config.SETTLEMENT_UNDER_CREDIT)

    # 2) SETTLEMENT_UNDER_CREDIT
    b.add_order("O000002", 12000, "completed")
    pid = b.add_payment("O000002", 12000, "settled", "ach", 50)
    b.add_fee(pid, 240, 60)
    sid = b.add_settlement(pid, 11700, 10200, "settled", 10)
    b.add_bank_credit(sid, 10200, 7)
    b.gt(pid, config.SETTLEMENT_UNDER_CREDIT)

    # 3) SETTLEMENT_UNDER_CREDIT
    b.add_order("O000003", 8000, "completed")
    pid = b.add_payment("O000003", 8000, "settled", "card", 70)
    b.add_fee(pid, 160, 40)
    sid = b.add_settlement(pid, 7800, 7000, "settled", 12)
    b.add_bank_credit(sid, 7000, 9)
    b.gt(pid, config.SETTLEMENT_UNDER_CREDIT)

    # 4) MISSING_SETTLEMENT
    b.add_order("O000004", 15000, "completed")
    pid = b.add_payment("O000004", 15000, "settled", "wire", 40)
    b.add_fee(pid, 300, 75)
    b.gt(pid, config.MISSING_SETTLEMENT)

    # 5) MISSING_SETTLEMENT
    b.add_order("O000005", 6000, "completed")
    pid = b.add_payment("O000005", 6000, "settled", "card", 90)
    b.add_fee(pid, 120, 30)
    b.gt(pid, config.MISSING_SETTLEMENT)

    # 6) MISSING_BANK_CREDIT
    b.add_order("O000006", 9000, "completed")
    pid = b.add_payment("O000006", 9000, "settled", "ach", 33)
    b.add_fee(pid, 180, 45)
    b.add_settlement(pid, 8775, 8775, "settled", 11)
    b.gt(pid, config.MISSING_BANK_CREDIT)

    # 7) MISSING_BANK_CREDIT
    b.add_order("O000007", 4500, "completed")
    pid = b.add_payment("O000007", 4500, "settled", "card", 66)
    b.add_fee(pid, 90, 22)
    b.add_settlement(pid, 4388, 4388, "settled", 14)
    b.gt(pid, config.MISSING_BANK_CREDIT)

    # 8) DUPLICATE_PAYMENT
    b.add_order("O000008", 7000, "completed")
    fa, ta = _fees_for(7000)
    for _ in range(2):
        p = b.add_payment("O000008", 7000, "settled", "card", 48)
        b.add_fee(p, fa, ta)
        s = b.add_settlement(p, 7000 - fa - ta, 7000 - fa - ta, "settled", 20)
        b.add_bank_credit(s, 7000 - fa - ta, 16)
    b.gt(p, config.DUPLICATE_PAYMENT)

    # 9) DUPLICATE_PAYMENT
    b.add_order("O000009", 3000, "completed")
    fa, ta = _fees_for(3000)
    for _ in range(2):
        p = b.add_payment("O000009", 3000, "settled", "wallet", 55)
        b.add_fee(p, fa, ta)
        s = b.add_settlement(p, 3000 - fa - ta, 3000 - fa - ta, "settled", 22)
        b.add_bank_credit(s, 3000 - fa - ta, 18)
    b.gt(p, config.DUPLICATE_PAYMENT)

    # 10) REFUND_EXCEEDS_PAYMENT
    b.add_order("O000010", 5000, "completed")
    pid = b.add_payment("O000010", 5000, "settled", "card", 60)
    b.add_refund(pid, 6000, 40)
    sid = b.add_settlement(pid, -1000, -1000, "settled", 30)
    b.add_bank_credit(sid, -1000, 25)
    b.gt(pid, config.REFUND_EXCEEDS_PAYMENT)

    # 11) REFUND_EXCEEDS_PAYMENT
    b.add_order("O000011", 2000, "completed")
    pid = b.add_payment("O000011", 2000, "settled", "ach", 75)
    b.add_refund(pid, 2500, 50)
    sid = b.add_settlement(pid, -500, -500, "settled", 33)
    b.add_bank_credit(sid, -500, 28)
    b.gt(pid, config.REFUND_EXCEEDS_PAYMENT)

    # 12) STATUS_MISMATCH
    b.add_order("O000012", 10000, "cancelled")
    pid = b.add_payment("O000012", 10000, "settled", "card", 44)
    fa, ta = _fees_for(10000)
    b.add_fee(pid, fa, ta)
    sid = b.add_settlement(pid, 10000 - fa - ta, 10000 - fa - ta, "settled", 20)
    b.add_bank_credit(sid, 10000 - fa - ta, 15)
    b.gt(pid, config.STATUS_MISMATCH)

    # 13) STATUS_MISMATCH
    b.add_order("O000013", 4000, "cancelled")
    pid = b.add_payment("O000013", 4000, "settled", "wallet", 38)
    fa, ta = _fees_for(4000)
    b.add_fee(pid, fa, ta)
    sid = b.add_settlement(pid, 4000 - fa - ta, 4000 - fa - ta, "settled", 18)
    b.add_bank_credit(sid, 4000 - fa - ta, 12)
    b.gt(pid, config.STATUS_MISMATCH)

    # 14) DUPLICATE_REFUND
    b.add_order("O000014", 8000, "completed")
    pid = b.add_payment("O000014", 8000, "settled", "card", 52)
    b.add_refund(pid, 500, 30)
    b.add_refund(pid, 500, 29)
    fa, ta = _fees_for(8000)
    b.add_fee(pid, fa, ta)
    expected = 8000 - 1000 - (fa + ta)
    sid = b.add_settlement(pid, expected, expected, "settled", 20)
    b.add_bank_credit(sid, expected, 16)
    b.gt(pid, config.DUPLICATE_REFUND)

    # 15) SETTLEMENT_UNDER_CREDIT (large)
    b.add_order("O000015", 25000, "completed")
    pid = b.add_payment("O000015", 25000, "settled", "wire", 80)
    b.add_fee(pid, 500, 125)
    sid = b.add_settlement(pid, 24375, 20000, "settled", 30)
    b.add_bank_credit(sid, 20000, 24)
    b.gt(pid, config.SETTLEMENT_UNDER_CREDIT)


CURATED_COUNT = 15


def build(records=None, seed=None, anomaly_rate=None):
    """Build the full in-memory dataset. Returns a Builder.

    `records` is the number of CANONICAL transactions (>= 15 so the curated
    set always fits). Anomalies beyond the curated 15 are injected into the
    bulk population at `anomaly_rate`.
    """
    records = int(records if records is not None else config.DATASET_SIZE)
    seed = int(seed if seed is not None else config.SEED)
    anomaly_rate = float(anomaly_rate if anomaly_rate is not None else config.ANOMALY_RATE)
    records = max(records, CURATED_COUNT)

    b = Builder(seed)
    methods = ["card", "ach", "wallet", "wire"]
    _add_curated(b)

    for i in range(CURATED_COUNT + 1, records + 1):
        oid = "O%06d" % i
        method = methods[b.rng.randint(0, len(methods) - 1)]
        if b.rng.random() < anomaly_rate:
            anomaly_type = INJECTABLE[b.rng.randint(0, len(INJECTABLE) - 1)]
            b.inject(oid, anomaly_type, method)
        else:
            amount = b.rng.randint(1000, 48000)
            refund = 0
            if b.rng.random() < 0.3:
                refund = b.rng.randint(50, amount // 5)
            b.clean_chain(oid, amount, refund=refund, method=method)

    return b


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_dataset(b, data_dir=None, records=None, seed=None, gen_ms=0.0):
    data_dir = data_dir or DATA_DIR
    _write_csv(os.path.join(data_dir, "orders.csv"), b.orders,
               ["order_id", "amount", "status"])
    _write_csv(os.path.join(data_dir, "payments.csv"), b.payments,
               ["payment_id", "order_id", "amount", "status", "method", "ts"])
    _write_csv(os.path.join(data_dir, "refunds.csv"), b.refunds,
               ["refund_id", "payment_id", "amount", "ts"])
    _write_csv(os.path.join(data_dir, "fees.csv"), b.fees,
               ["fee_id", "payment_id", "fee_amt", "tax_amt"])
    _write_csv(os.path.join(data_dir, "settlements.csv"), b.settlements,
               ["settlement_id", "payment_id", "expected_amt", "actual_amt", "status", "ts"])
    _write_csv(os.path.join(data_dir, "bank_credits.csv"), b.bank_credits,
               ["credit_id", "settlement_id", "amount", "ts"])
    with open(os.path.join(data_dir, "ground_truth.json"), "w") as f:
        json.dump(b.ground_truth, f, indent=2)

    meta = {
        "canonical_transactions": len(b.orders),
        "records": records if records is not None else len(b.orders),
        "seed": seed if seed is not None else config.SEED,
        "total_records": b.total_records(),
        "table_counts": {k: len(v) for k, v in b.tables().items()},
        "planted_anomalies": len(b.ground_truth),
        "generation_time_ms": round(gen_ms, 2),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    with open(os.path.join(data_dir, "dataset_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the CaseFile dataset.")
    parser.add_argument("--records", type=int, default=config.DATASET_SIZE,
                        help="number of canonical transactions (default from CASEFILE_DATASET_SIZE)")
    parser.add_argument("--seed", type=int, default=config.SEED,
                        help="RNG seed (default from CASEFILE_SEED)")
    parser.add_argument("--anomaly-rate", type=float, default=config.ANOMALY_RATE,
                        help="fraction of bulk transactions that get an injected anomaly")
    parser.add_argument("--out-dir", default=DATA_DIR)
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    b = build(records=args.records, seed=args.seed, anomaly_rate=args.anomaly_rate)
    gen_ms = (time.perf_counter() - t0) * 1000.0
    meta = write_dataset(b, data_dir=args.out_dir, records=args.records,
                         seed=args.seed, gen_ms=gen_ms)

    print("Dataset written to", args.out_dir)
    print("  canonical transactions: %d" % meta["canonical_transactions"])
    print("  total relational records: %d" % meta["total_records"])
    for k, v in meta["table_counts"].items():
        print("    %-14s %d" % (k + ":", v))
    print("  planted anomalies: %d" % meta["planted_anomalies"])
    print("  generation time: %.1f ms  (%.0f records/sec)"
          % (gen_ms, meta["total_records"] / (gen_ms / 1000.0) if gen_ms else 0))


if __name__ == "__main__":
    main()
