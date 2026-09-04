from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import config
from ..models.schemas import AuditRunResponse, Case, FailureModeResponse, PaginatedCases
from . import store

router = APIRouter(prefix="/api", tags=["cases"])


@router.post("/audit/run", response_model=AuditRunResponse)
def run_audit(mode: str = Query("normal", pattern="^(normal|failure)$")):
    """Run the audit and return the summary plus the top priority-ranked cases.

    The full case set can be large (thousands on a 100K dataset), so the browser
    never receives all of them here — it gets the summary and the top
    MAX_CASES_RETURNED. Use the paginated /api/cases for the complete list.
    """
    result = store.run(mode)
    return {
        "mode": result["mode"],
        "summary": result["summary"],
        "cases": result["cases"][: config.MAX_CASES_RETURNED],
    }


@router.get("/cases", response_model=PaginatedCases)
def list_cases(
    mode: str = Query("normal", pattern="^(normal|failure)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(config.DEFAULT_PAGE_SIZE, ge=1, le=500),
):
    return store.paginate_cases(mode, page, page_size)


@router.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: str, mode: str = Query("normal", pattern="^(normal|failure)$")):
    case = store.get_case(case_id, mode)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


class BankFeedToggle(BaseModel):
    offline: bool = True


@router.post("/failure-mode/bank-feed", response_model=FailureModeResponse)
def toggle_bank_feed(body: BankFeedToggle = BankFeedToggle()):
    """Simulate the bank-credit feed going offline (or coming back).

    Flips server-side state and re-runs the audit against the degraded
    evidence — confidence and classification change because the *evidence*
    changed in the backend, never because the UI faked it.
    """
    store.set_bank_feed_offline(body.offline)
    mode = "failure" if body.offline else "normal"
    result = store.run(mode)
    return {"bank_feed_offline": body.offline, "mode": mode, "summary": result["summary"]}
