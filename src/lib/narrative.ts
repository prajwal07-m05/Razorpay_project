import type { Case, Investigation, AnomalyType } from "./types"
import { money } from "./engine"

/**
 * OFFLINE FALLBACK investigation. The authoritative path is a real Claude call
 * in the backend (llm/investigator.py) via POST /api/cases/{id}/investigate.
 * This deterministic version keeps the preview coherent when the backend is
 * unreachable and is clearly stamped generated_by:"fallback". It reasons over
 * the structured evidence and introduces NO new numbers — every figure it
 * cites was computed by the deterministic engine.
 */
export function buildInvestigation(c: Case): Investigation {
  const dv = c.evidence_packet.derived_values
  const complete = c.evidence_packet.evidence_complete
  const amt = money(c.amount_at_risk)

  const facts = [
    `Gross payment captured: ${money(dv.gross_payment)} on ${c.payment_id} (${c.method}).`,
    `Refunds ${money(dv.refund_total)}, fees ${money(dv.fee_total)} → expected settlement ${money(dv.expected_settlement)}.`,
    c.evidence_packet.settlement
      ? `Actual settlement recorded: ${money(dv.actual_settlement)}.`
      : `No settlement record exists for this payment.`,
    complete
      ? `Bank credit ${money(dv.bank_credit_amount)}.`
      : `Bank-credit feed is offline — downstream confirmation unavailable.`,
  ]

  const hypothesis: Record<AnomalyType, string> = {
    DUPLICATE_PAYMENT: "The order carries more than one captured payment; the evidence is consistent with a duplicate capture holding excess funds against a single fulfilment.",
    MISSING_SETTLEMENT: "A captured payment produced no settlement record; the evidence is consistent with funds stranded before entering the settlement pipeline.",
    REFUND_EXCEEDS_PAYMENT: "Cumulative refunds exceed the amount captured; the evidence is consistent with an over-refund returning more than was collected.",
    SETTLEMENT_UNDER_CREDIT: `Expected and actual settlement diverge by ${amt} beyond refunds and fees; the evidence is consistent with a settlement under-credit.`,
    MISSING_BANK_CREDIT: "The settlement is marked settled but no matching bank credit is present; the evidence is consistent with a payout that has not landed.",
    STATUS_MISMATCH: "The payment is captured while the order is not marked paid; the evidence is consistent with a ledger status desync.",
  }

  const action: Record<AnomalyType, string> = {
    DUPLICATE_PAYMENT: `Draft a refund of the ${amt} excess capture for human approval — do not auto-refund.`,
    MISSING_SETTLEMENT: `Draft a settlement-trace ticket for ${amt} and hold for approval.`,
    REFUND_EXCEEDS_PAYMENT: `Freeze further refunds and draft a ${amt} clawback correction for approval.`,
    SETTLEMENT_UNDER_CREDIT: `Draft a settlement-discrepancy investigation for the ${amt} gap and hold for approval.`,
    MISSING_BANK_CREDIT: `Draft a bank-reconciliation trace for the ${amt} settlement and hold for approval.`,
    STATUS_MISMATCH: `Draft an order-status correction to realign the ledgers — bookkeeping only, no money moves.`,
  }

  const alternatives = complete
    ? [
        "Timing skew between systems (would resolve on the next settlement cycle).",
        "A legitimate manual adjustment not yet reflected in the fee/refund tables.",
      ]
    : [
        "The bank credit may have landed but is not visible while the feed is offline.",
        "The discrepancy may be a reporting artifact of the missing source rather than a real loss.",
      ]

  return {
    summary: `${c.title}. ${amt} of exposure on ${c.payment_id} / ${c.order_id}. Classification: ${c.classification}.`,
    facts,
    root_cause_hypothesis: hypothesis[c.type],
    alternative_explanations: alternatives,
    contradictory_evidence: c.evidence_packet.conflicts.length ? c.evidence_packet.conflicts : ["None identified in the available evidence."],
    evidence_sufficiency: complete ? "SUFFICIENT" : "INSUFFICIENT",
    recommended_action: complete
      ? action[c.type]
      : "Insufficient evidence for a confident recommendation. Route to a human to restore the missing feed and re-run before any action.",
    reasoning: complete
      ? "All required evidence sources were present and read cleanly, so the deterministic finding is asserted with full base confidence. The agent recommends a bounded draft only — it holds a license to investigate, not to act."
      : "A required evidence source is offline. The discrepancy is observable but the actual merchant loss cannot be conclusively established, so confidence is capped and the case is routed to human review rather than asserted.",
    generated_by: "fallback",
  }
}
