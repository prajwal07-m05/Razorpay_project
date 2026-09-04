"""Precision / recall / F1 scoring against ground truth. Pure Python.

This module NEVER reads ground_truth.json itself; the caller passes the
ground-truth list in. Matching key = (payment_id, type).
"""


def compute_metrics(run_result, ground_truth, records_processed=None, processing_time_ms=0):
    cases = run_result["cases"]
    summary = run_result.get("summary", {})
    detected = set()
    for c in cases:
        detected.add((c["payment_id"], c["type"]))

    truth = set((g["payment_id"], g["type"]) for g in ground_truth)

    tp = len(detected & truth)
    fp = len(detected - truth)
    fn = len(truth - detected)

    records = (records_processed if records_processed is not None
               else summary.get("records_processed", 0))
    # True negatives: transactions the engine correctly left alone. Approximate
    # as (records processed) minus everything that was flagged or planted.
    tn = max(0, records - tp - fp - fn)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    potential_exposure = sum(c["amount_at_risk"] for c in cases)
    exception_cases = [c for c in cases if c["classification"] == "EXCEPTION"]
    review_cases = [c for c in cases if c["classification"] == "NEEDS_HUMAN_REVIEW"]
    unexplained_exposure = sum(c["amount_at_risk"] for c in exception_cases)
    avg_conf = round(sum(c["confidence"] for c in cases) / len(cases), 1) if cases else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "records_processed": records,
        "anomalies_planted": len(truth),
        "anomalies_detected": len(detected),
        "potential_exposure": potential_exposure,
        "processing_time_ms": processing_time_ms,
        # Benchmark + exposure breakdown (sourced from the enriched summary).
        "canonical_transactions": summary.get("canonical_transactions", 0),
        "total_records": summary.get("total_records", 0),
        "records_per_second": summary.get("records_per_second", 0.0),
        "generation_time_ms": summary.get("generation_ms", 0.0),
        "loading_time_ms": summary.get("loading_ms", 0.0),
        "reconciliation_ms": summary.get("reconciliation_ms", 0.0),
        "explained_cases": summary.get("explained", 0),
        "exception_cases": len(exception_cases),
        "review_cases": len(review_cases),
        "unexplained_exposure": unexplained_exposure,
        "average_confidence": avg_conf,
    }
