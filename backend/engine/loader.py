"""CSV -> records boundary. THE ONLY module that imports pandas.

Everything downstream operates on plain list[dict] records.
"""
import os

import pandas as pd

TABLES = ["orders", "payments", "refunds", "fees", "settlements", "bank_credits"]

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load_all(data_dir=None):
    """Load the six CSVs into a dict of table-name -> list[dict] records."""
    data_dir = data_dir or _DATA_DIR
    tables = {}
    for name in TABLES:
        path = os.path.join(data_dir, name + ".csv")
        if os.path.exists(path):
            tables[name] = pd.read_csv(path).to_dict("records")
        else:
            tables[name] = []
    return tables
