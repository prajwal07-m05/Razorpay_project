"""Shared in-memory state for the API layer.

The dataset is deterministic and large (up to 100K+ canonical transactions),
so we load the CSVs once and CACHE the full audit result per mode. Recomputing
100K chains on every request would be wasteful; the cache is invalidated when
the failure-mode toggle flips. Investigations and approvals are stored in
memory keyed by case_id and merged into responses.
"""
import json
import os
import time

from ..engine import audit_engine, loader

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_META_PATH = os.path.join(_DATA_DIR, "dataset_meta.json")

_tables = None
_load_ms = 0.0
_meta = None

# mode -> cached run result (enriched). Cleared on reset / feed toggle.
_run_cache = {}
_recon_ms = {}

# case_id -> Investigation dict / approval entry
_investigations = {}
_approvals = {}

# Server-side failure-mode flag. The API also accepts an explicit ?mode= query
# param; POST /api/failure-mode/bank-feed flips this default.
_bank_feed_offline = False


def _load_meta():
    global _meta
    if _meta is None:
        if os.path.exists(_META_PATH):
            with open(_META_PATH) as f:
                _meta = json.load(f)
        else:
            _meta = {}
    return _meta


def get_tables():
    global _tables, _load_ms
    if _tables is None:
        t0 = time.perf_counter()
        _tables = loader.load_all()
        _load_ms = (time.perf_counter() - t0) * 1000.0
    return _tables


def _enrich_summary(result, mode):
    """Attach dataset-scale + benchmark fields to the run summary."""
    meta = _load_meta()
    cases = result["cases"]
    summary = result["summary"]

    total_records = meta.get("total_records") or sum(len(v) for v in get_tables().values())
    canonical = meta.get("canonical_transactions") or len(get_tables().get("orders", []))

    exception_exposure = sum(
        c["amount_at_risk"] for c in cases if c["classification"] == "EXCEPTION"
    )
    avg_conf = round(sum(c["confidence"] for c in cases) / len(cases), 1) if cases else 0.0
    recon_ms = _recon_ms.get(mode, 0.0)
    records_processed = summary["records_processed"]

    summary.update({
        "canonical_transactions": canonical,
        "total_records": total_records,
        "unexplained_exposure": exception_exposure,
        "average_confidence": avg_conf,
        "reconciliation_ms": round(recon_ms, 2),
        "loading_ms": round(_load_ms, 2),
        "generation_ms": meta.get("generation_time_ms", 0.0),
        "records_per_second": round(records_processed / (recon_ms / 1000.0)) if recon_ms else 0,
        "total_cases": len(cases),
    })
    return result


def _compute(mode):
    t0 = time.perf_counter()
    result = audit_engine.run_audit(get_tables(), mode=mode)
    _recon_ms[mode] = (time.perf_counter() - t0) * 1000.0
    return _enrich_summary(result, mode)


def _effective_mode(mode):
    if mode is None:
        return "failure" if _bank_feed_offline else "normal"
    return mode


def run(mode="normal"):
    """Return the cached (or freshly computed) audit for a mode, with stored
    investigations merged in."""
    mode = _effective_mode(mode)
    if mode not in _run_cache:
        _run_cache[mode] = _compute(mode)
    result = _run_cache[mode]
    for case in result["cases"]:
        inv = _investigations.get(case["case_id"])
        case["investigation"] = inv if inv is not None else None
    return result


def get_case(case_id, mode="normal"):
    for case in run(mode)["cases"]:
        if case["case_id"] == case_id:
            return case
    return None


def paginate_cases(mode, page, page_size):
    result = run(mode)
    cases = result["cases"]
    total = len(cases)
    page = max(1, page)
    start = (page - 1) * page_size
    items = cases[start:start + page_size]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def set_bank_feed_offline(offline):
    global _bank_feed_offline
    _bank_feed_offline = bool(offline)
    return _bank_feed_offline


def bank_feed_offline():
    return _bank_feed_offline


def store_investigation(case_id, investigation_dict):
    _investigations[case_id] = investigation_dict


def store_approval(case_id, entry):
    _approvals[case_id] = entry


def reset():
    global _tables, _meta, _load_ms
    _tables = None
    _meta = None
    _load_ms = 0.0
    _run_cache.clear()
    _recon_ms.clear()
    _investigations.clear()
    _approvals.clear()
