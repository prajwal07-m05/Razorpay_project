from fastapi import APIRouter, HTTPException

from ..audit import audit_log
from ..models.schemas import ApproveRequest, ApproveResponse
from . import store

router = APIRouter(prefix="/api", tags=["approve"])


@router.post("/cases/{case_id}/approve", response_model=ApproveResponse)
def approve_case(case_id: str, body: ApproveRequest = ApproveRequest()):
    case = store.get_case(case_id, "normal")
    if case is None:
        case = store.get_case(case_id, "failure")
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    actor = body.actor or "human_reviewer"
    # Human-in-the-loop: this approves a draft only. It MUST NOT move money.
    entry = audit_log.log(
        audit_log.HUMAN_APPROVAL,
        case_id,
        actor=actor,
        result="approved (draft only; no funds moved)",
    )
    store.store_approval(case_id, entry)
    return {"audit_entry": entry}
