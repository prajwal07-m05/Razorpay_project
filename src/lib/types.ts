// Shared contract with the FastAPI backend. snake_case mirrors the JSON the
// backend returns so responses map 1:1 with no translation layer.

export type AnomalyType =
  | "MISSING_SETTLEMENT"
  | "DUPLICATE_PAYMENT"
  | "REFUND_EXCEEDS_PAYMENT"
  | "STATUS_MISMATCH"
  | "MISSING_BANK_CREDIT"
  | "SETTLEMENT_UNDER_CREDIT"

export type Tier = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"

export type Classification =
  | "EXPLAINED"
  | "EXCEPTION"
  | "NEEDS_HUMAN_REVIEW"
  | "CONFLICTING_EVIDENCE"

export type Mode = "normal" | "failure"
export type EvidenceStatus = "ok" | "broken" | "missing"

export interface Order {
  order_id: string
  amount: number
  status: string
}
export interface Payment {
  payment_id: string
  order_id: string
  amount: number
  status: string
  method: string
  ts: string
}
export interface Refund {
  refund_id: string
  payment_id: string
  amount: number
  ts: string
}
export interface Fee {
  fee_id: string
  payment_id: string
  fee_amt: number
  tax_amt: number
}
export interface Settlement {
  settlement_id: string
  payment_id: string
  expected_amt: number
  actual_amt: number
  status: string
  ts: string
}
export interface BankCredit {
  credit_id: string
  settlement_id: string
  amount: number
  ts: string
}

export interface Dataset {
  orders: Order[]
  payments: Payment[]
  refunds: Refund[]
  fees: Fee[]
  settlements: Settlement[]
  bank_credits: BankCredit[]
}

export interface GroundTruthEntry {
  payment_id: string
  type: AnomalyType
}

export interface DerivedValues {
  gross_payment: number
  refund_total: number
  fee_total: number
  expected_settlement: number
  actual_settlement: number | null
  bank_credit_amount: number | null
  unexplained_gap: number
}

export interface EvidencePacket {
  order: Order | null
  payment: Payment
  refunds: Refund[]
  fees: Fee[]
  settlement: Settlement | null
  bank_credit: BankCredit | null
  derived_values: DerivedValues
  conflicts: string[]
  missing_evidence: string[]
  evidence_complete: boolean
}

export interface EvidenceItem {
  source: string
  label: string
  value: string
  status: EvidenceStatus
}

export interface ChainNode {
  stage: string
  id: string
  label: string
  value: string
  status: EvidenceStatus
}

export interface Investigation {
  summary: string
  facts: string[]
  root_cause_hypothesis: string
  alternative_explanations: string[]
  contradictory_evidence: string[]
  evidence_sufficiency: "SUFFICIENT" | "INSUFFICIENT"
  recommended_action: string
  reasoning: string
  generated_by: "gemini" | "openai" | "claude" | "fallback" | "unavailable"
}

export interface Case {
  case_id: string
  payment_id: string
  order_id: string
  type: AnomalyType
  title: string
  classification: Classification
  amount_at_risk: number
  base_confidence: number
  confidence: number
  age_hours: number
  priority_score: number
  tier: Tier
  method: string
  evidence_packet: EvidencePacket
  evidence_items: EvidenceItem[]
  chain: ChainNode[]
  investigation: Investigation | null
}

export interface RunSummary {
  records_processed: number
  reconciled: number
  explained: number
  exceptions: number
  needs_review: number
  potential_exposure: number
  // Dataset-scale + benchmark fields (backend only; optional for the offline
  // dev fallback, which does not simulate 100K).
  canonical_transactions?: number
  total_records?: number
  total_cases?: number
  unexplained_exposure?: number
  average_confidence?: number
  reconciliation_ms?: number
  loading_ms?: number
  generation_ms?: number
  records_per_second?: number
}

export interface AuditRun {
  mode: Mode
  summary: RunSummary
  cases: Case[]
}

export interface Metrics {
  precision: number
  recall: number
  f1: number
  true_positives: number
  false_positives: number
  false_negatives: number
  records_processed: number
  anomalies_planted: number
  anomalies_detected: number
  potential_exposure: number
  processing_time_ms: number
  true_negatives?: number
  canonical_transactions?: number
  total_records?: number
  records_per_second?: number
  generation_time_ms?: number
  loading_time_ms?: number
  reconciliation_ms?: number
  explained_cases?: number
  exception_cases?: number
  review_cases?: number
  unexplained_exposure?: number
  average_confidence?: number
}

export interface AuditEntry {
  timestamp: string
  case_id: string
  action: string
  actor: string
  result: string
}
