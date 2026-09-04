"""Pydantic models for the API contract (snake_case as the frontend expects)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DerivedValues(BaseModel):
    gross_payment: float
    refund_total: float
    fee_total: float
    expected_settlement: float
    actual_settlement: Optional[float] = None
    bank_credit_amount: Optional[float] = None
    unexplained_gap: Optional[float] = None


class EvidencePacket(BaseModel):
    case_id: str
    order: Optional[Dict[str, Any]] = None
    payment: Optional[Dict[str, Any]] = None
    refunds: List[Dict[str, Any]] = Field(default_factory=list)
    fees: List[Dict[str, Any]] = Field(default_factory=list)
    settlement: Optional[Dict[str, Any]] = None
    bank_credit: Optional[Dict[str, Any]] = None
    derived_values: DerivedValues
    conflicts: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    evidence_complete: bool


class EvidenceItem(BaseModel):
    source: str
    label: str
    value: Optional[Any] = None
    status: str  # ok | broken | missing


class ChainStage(BaseModel):
    stage: str
    id: Optional[str] = None
    label: str
    value: Optional[Any] = None
    status: str  # ok | broken | missing


class Investigation(BaseModel):
    summary: str
    facts: List[str] = Field(default_factory=list)
    root_cause_hypothesis: str
    alternative_explanations: List[str] = Field(default_factory=list)
    contradictory_evidence: List[str] = Field(default_factory=list)
    evidence_sufficiency: str  # SUFFICIENT | INSUFFICIENT
    recommended_action: str
    reasoning: str
    generated_by: str  # gemini | openai | claude | fallback | unavailable


class Case(BaseModel):
    case_id: str
    payment_id: str
    order_id: str
    type: str
    title: str
    classification: str
    amount_at_risk: float
    base_confidence: int
    confidence: int
    age_hours: float
    priority_score: float
    tier: str
    method: Optional[str] = None
    evidence_packet: EvidencePacket
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    chain: List[ChainStage] = Field(default_factory=list)
    investigation: Optional[Investigation] = None


class AuditSummary(BaseModel):
    records_processed: int
    reconciled: int
    explained: int
    exceptions: int
    needs_review: int
    potential_exposure: float
    bank_feed_available: bool = True
    # Dataset-scale + benchmark fields (populated by the API store).
    canonical_transactions: int = 0
    total_records: int = 0
    total_cases: int = 0
    unexplained_exposure: float = 0.0
    average_confidence: float = 0.0
    reconciliation_ms: float = 0.0
    loading_ms: float = 0.0
    generation_ms: float = 0.0
    records_per_second: float = 0.0


class AuditRunResponse(BaseModel):
    mode: str
    summary: AuditSummary
    cases: List[Case]


class PaginatedCases(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Case]


class FailureModeResponse(BaseModel):
    bank_feed_offline: bool
    mode: str
    summary: AuditSummary


class Metrics(BaseModel):
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int = 0
    records_processed: int
    anomalies_planted: int
    anomalies_detected: int
    potential_exposure: float
    processing_time_ms: float
    # Benchmark + exposure breakdown (measured, never fabricated).
    canonical_transactions: int = 0
    total_records: int = 0
    records_per_second: float = 0.0
    generation_time_ms: float = 0.0
    loading_time_ms: float = 0.0
    reconciliation_ms: float = 0.0
    explained_cases: int = 0
    exception_cases: int = 0
    review_cases: int = 0
    unexplained_exposure: float = 0.0
    average_confidence: float = 0.0


class AuditEntry(BaseModel):
    timestamp: str
    case_id: Optional[str] = None
    action: str
    actor: str
    result: str


class ApproveRequest(BaseModel):
    actor: Optional[str] = "human_reviewer"


class ApproveResponse(BaseModel):
    audit_entry: AuditEntry
