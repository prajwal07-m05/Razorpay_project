"""In-memory, append-only audit trail.

Records the immutable sequence of actions taken on a case. The AI is only
ever permitted to INVESTIGATE / CLASSIFY / CREATE_CASE / DRAFT / RECOMMEND;
moving money is never an available action.
"""
from datetime import datetime, timezone

# Canonical event names.
CASE_CREATED = "CASE_CREATED"
EVIDENCE_ASSEMBLED = "EVIDENCE_ASSEMBLED"
AI_INVESTIGATION_STARTED = "AI_INVESTIGATION_STARTED"
AI_INVESTIGATION_COMPLETED = "AI_INVESTIGATION_COMPLETED"
RECOMMENDATION_GENERATED = "RECOMMENDATION_GENERATED"
HUMAN_APPROVAL = "HUMAN_APPROVAL"

AI_ALLOWED_ACTIONS = {"INVESTIGATE", "CLASSIFY", "CREATE_CASE", "DRAFT", "RECOMMEND"}

_LOG = []


def log(action, case_id=None, actor="system", result="ok"):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_id": case_id,
        "action": action,
        "actor": actor,
        "result": result,
    }
    _LOG.append(entry)
    return entry


def all_entries():
    return list(_LOG)


def reset():
    _LOG.clear()
