"""CSV -> records boundary.

The production dataset is large, so this loader intentionally avoids the
pandas DataFrame -> list[dict] double-allocation. CSV rows are converted
directly into plain Python dictionaries with numeric money fields parsed once.

Everything downstream operates on plain list[dict] records.
"""

import csv
import os

TABLES = [
    "orders",
    "payments",
    "refunds",
    "fees",
    "settlements",
    "bank_credits",
]

NUMERIC_FIELDS = {
    "amount",
    "fee_amt",
    "tax_amt",
    "expected_amt",
    "actual_amt",
}


_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
)


def _parse_number(value):
    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_row(row):
    parsed = {}

    for key, value in row.items():
        if key in NUMERIC_FIELDS:
            parsed[key] = _parse_number(value)
        else:
            parsed[key] = value

    return parsed


def load_all(data_dir=None):
    """Load the six CSVs into a dict of table-name -> list[dict] records."""
    data_dir = data_dir or _DATA_DIR

    tables = {}

    for name in TABLES:
        path = os.path.join(data_dir, name + ".csv")

        if not os.path.exists(path):
            tables[name] = []
            continue

        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            tables[name] = [_parse_row(row) for row in reader]

    return tables
