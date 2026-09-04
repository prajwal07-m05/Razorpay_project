from fastapi import APIRouter, HTTPException, Query

from ..audit import audit_log
from ..llm import investigator
from ..models.schemas import Investigation
from . import store

router = APIRouter(prefix="/api", tags=["investigate"])


@router.post("/cases/{case_id}/investigate", response_model=Investigation)
def investigate_case(case_id: str, mode: str = Query("normal", pattern="^(normal|failure)$")):
    case = store.get_case(case_id, mode)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    audit_log.log(audit_log.EVIDENCE_ASSEMBLED, case_id, actor="engine")
    audit_log.log(audit_log.AI_INVESTIGATION_STARTED, case_id, actor="ai:INVESTIGATE")

    investigation = investigator.investigate(case)

    audit_log.log(
        audit_log.AI_INVESTIGATION_COMPLETED,
        case_id,
        actor="ai:INVESTIGATE",
        result=investigation.generated_by,
    )
    audit_log.log(
        audit_log.RECOMMENDATION_GENERATED,
        case_id,
        actor="ai:RECOMMEND",
        result=investigation.recommended_action,
    )

    store.store_investigation(case_id, investigation.model_dump())
    return investigation
