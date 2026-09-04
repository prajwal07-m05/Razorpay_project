"""Metrics endpoint. This is the ONLY module permitted to read ground_truth."""
import json
import os

from fastapi import APIRouter, Query

from ..engine import metrics as metrics_engine
from ..models.schemas import Metrics
from . import store

router = APIRouter(prefix="/api", tags=["metrics"])

_GROUND_TRUTH_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ground_truth.json"
)


def _load_ground_truth():
    with open(_GROUND_TRUTH_PATH) as f:
        return json.load(f)


@router.get("/metrics", response_model=Metrics)
def get_metrics(mode: str = Query("normal", pattern="^(normal|failure)$")):
    result = store.run(mode)
    ground_truth = _load_ground_truth()
    # Report the actual reconciliation time measured by the store (from the
    # engine run), not the cache-hit lookup time here.
    processing_ms = result["summary"].get("reconciliation_ms", 0.0)
    return metrics_engine.compute_metrics(
        result,
        ground_truth,
        records_processed=result["summary"]["records_processed"],
        processing_time_ms=round(processing_ms, 3),
    )
