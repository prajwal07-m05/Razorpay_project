from typing import List

from fastapi import APIRouter

from ..audit import audit_log
from ..models.schemas import AuditEntry

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit-log", response_model=List[AuditEntry])
def get_audit_log():
    return audit_log.all_entries()
