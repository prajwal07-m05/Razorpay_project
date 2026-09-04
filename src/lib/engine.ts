import type {
  Case,
  Dataset,
  EvidenceItem,
  EvidencePacket,
  ChainNode,
  DerivedValues,
  AnomalyType,
  Classification,
  Tier,
  Mode,
  GroundTruthEntry,
  Metrics,
  RunSummary,
  Order,
  Payment,
  Settlement,
  BankCredit,
} from "./types"
import { buildInvestigation } from "./narrative"

const INR = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 })
export function money(n: number | null | undefined): string {
  if (n == null) return "—"
  return "₹" + INR.format(Math.round(n))
}
const round2 = (n: number) => Math.round(n * 100) / 100

// ── Config (mirrors backend/config.py) ────────────────────────────────────
const BASE_CONFIDENCE: Record<AnomalyType, number> = {
  DUPLICATE_PAYMENT: 99,
  MISSING_SETTLEMENT: 94,
  REFUND_EXCEEDS_PAYMENT: 96,
  SETTLEMENT_UNDER_CREDIT: 93,
  MISSING_BANK_CREDIT: 90,
  STATUS_MISMATCH: 85,
}
const SEVERITY: Record<AnomalyType, number> = {
  DUPLICATE_PAYMENT: 1.0,
  MISSING_SETTLEMENT: 1.0,
  REFUND_EXCEEDS_PAYMENT: 0.9,
  SETTLEMENT_UNDER_CREDIT: 1.0,
  MISSING_BANK_CREDIT: 0.8,
  STATUS_MISMATCH: 0.6,
}
const DEGRADED_CAP = 52
const TITLES: Record<AnomalyType, string> = {
  DUPLICATE_PAYMENT: "Duplicate payment captured",
  MISSING_SETTLEMENT: "Captured payment never settled",
  REFUND_EXCEEDS_PAYMENT: "Refund exceeds original payment",
  SETTLEMENT_UNDER_CREDIT: "Settlement under-credited",
  MISSING_BANK_CREDIT: "Settled but no bank credit received",
  STATUS_MISMATCH: "Order / payment status mismatch",
}
const NOW = Date.parse("2026-08-30T18:00:00Z")

function ageHours(ts: string) {
  return Math.max(1, Math.round((NOW - Date.parse(ts)) / 3600_000))
}
function tierFor(score: number): Tier {
  if (score >= 14000) return "CRITICAL"
  if (score >= 6000) return "HIGH"
  if (score >= 2000) return "MEDIUM"
  return "LOW"
}

interface Ctx {
  order?: Order
  fee?: { fee_amt: number; tax_amt: number }
  settlement?: Settlement
  credit?: BankCredit
  refundTotal: number
  bankFeedAvailable: boolean
}

/**
 * Deterministic engine. Walks Order→Payment→Refund→Fee→Settlement→Bank-credit
 * per transaction, classifies each chain as EXPLAINED / EXCEPTION /
 * NEEDS_HUMAN_REVIEW, and raises a Case for anything not fully explained.
 * `mode === "failure"` drops the bank-credit feed — settlement discrepancies
 * become unverifiable and degrade to review rather than being asserted.
 */
export function runAudit(dataset: Dataset, mode: Mode = "normal"): Case[] {
  const { orders, payments, refunds, fees, settlements } = dataset
  const bankCredits = mode === "failure" ? [] : dataset.bank_credits
  const bankFeedAvailable = mode === "normal"

  const orderById = new Map(orders.map((o) => [o.order_id, o]))
  const paymentsByOrder = new Map<string, Payment[]>()
  for (const p of payments) {
    const arr = paymentsByOrder.get(p.order_id) ?? []
    arr.push(p)
    paymentsByOrder.set(p.order_id, arr)
  }
  const refundsByPayment = new Map<string, typeof refunds>()
  for (const r of refunds) {
    const arr = refundsByPayment.get(r.payment_id) ?? []
    arr.push(r)
    refundsByPayment.set(r.payment_id, arr)
  }
  const feeByPayment = new Map(fees.map((f) => [f.payment_id, f]))
  const settlementByPayment = new Map(settlements.map((s) => [s.payment_id, s]))
  const creditBySettlement = new Map(bankCredits.map((c) => [c.settlement_id, c]))

  const cases: Case[] = []
  const seenDuplicateOrders = new Set<string>()

  for (const p of payments) {
    if (p.status !== "captured") continue
    const order = orderById.get(p.order_id)
    const fee = feeByPayment.get(p.payment_id)
    const settlement = settlementByPayment.get(p.payment_id)
    const refundList = refundsByPayment.get(p.payment_id) ?? []
    const credit = settlement ? creditBySettlement.get(settlement.settlement_id) : undefined
    const refundTotal = round2(refundList.reduce((s, r) => s + r.amount, 0))
    const sameOrderCaptured = (paymentsByOrder.get(p.order_id) ?? []).filter((x) => x.status === "captured")
    const ctx: Ctx = { order, fee, settlement, credit, refundTotal, bankFeedAvailable }

    if (sameOrderCaptured.length > 1 && seenDuplicateOrders.has(p.order_id)) continue

    // Rule — duplicate payment.
    if (sameOrderCaptured.length > 1) {
      seenDuplicateOrders.add(p.order_id)
      const dupTotal = round2(sameOrderCaptured.reduce((s, x) => s + x.amount, 0))
      cases.push(mk("DUPLICATE_PAYMENT", p, ctx, dupTotal - p.amount, dataset))
      continue
    }
    // Rule — status mismatch.
    if (order && order.status !== "paid") {
      cases.push(mk("STATUS_MISMATCH", p, ctx, p.amount, dataset))
      continue
    }
    // Rule — refund exceeds payment.
    if (refundTotal > p.amount) {
      cases.push(mk("REFUND_EXCEEDS_PAYMENT", p, ctx, refundTotal - p.amount, dataset))
      continue
    }
    // Rule — missing settlement.
    if (!settlement) {
      const feeTotal = fee ? round2(fee.fee_amt + fee.tax_amt) : 0
      cases.push(mk("MISSING_SETTLEMENT", p, ctx, round2(p.amount - refundTotal - feeTotal), dataset))
      continue
    }
    // Rule — settled but no bank credit. Only observable while the feed is
    // live; when the feed is offline we cannot see credits at all, so this
    // class of detection is (honestly) lost rather than raised against every
    // settlement. Balanced settlements stay explained; the missing feed is
    // surfaced as a global caveat, not hundreds of cases.
    if (bankFeedAvailable && settlement.status === "settled" && !credit) {
      cases.push(mk("MISSING_BANK_CREDIT", p, ctx, settlement.actual_amt, dataset))
      continue
    }
    // Rule — settlement under-credit (unexplained gap between expected & actual).
    const feeTotal = fee ? round2(fee.fee_amt + fee.tax_amt) : 0
    const expected = round2(p.amount - refundTotal - feeTotal)
    const gap = round2(expected - settlement.actual_amt)
    if (Math.abs(gap) > 1) {
      cases.push(mk("SETTLEMENT_UNDER_CREDIT", p, ctx, Math.abs(gap), dataset))
      continue
    }
    // Otherwise: expected == actual == bank credit → EXPLAINED, not raised.
  }

  return cases.sort((a, b) => b.priority_score - a.priority_score)
}

function derive(p: Payment, ctx: Ctx): DerivedValues {
  const feeTotal = ctx.fee ? round2(ctx.fee.fee_amt + ctx.fee.tax_amt) : 0
  const expected = round2(p.amount - ctx.refundTotal - feeTotal)
  const actual = ctx.settlement ? ctx.settlement.actual_amt : null
  const bank = ctx.bankFeedAvailable ? (ctx.credit ? ctx.credit.amount : null) : null
  return {
    gross_payment: p.amount,
    refund_total: ctx.refundTotal,
    fee_total: feeTotal,
    expected_settlement: expected,
    actual_settlement: actual,
    bank_credit_amount: bank,
    unexplained_gap: actual == null ? expected : round2(expected - actual),
  }
}

function mk(
  type: AnomalyType,
  p: Payment,
  ctx: Ctx,
  amountAtRisk: number,
  dataset: Dataset,
): Case {
  const dv = derive(p, ctx)
  const conflicts: string[] = []
  const missing: string[] = []

  // Required-source availability drives evidence completeness.
  const needsBankFeed = type === "MISSING_BANK_CREDIT" || type === "SETTLEMENT_UNDER_CREDIT"
  if (needsBankFeed && !ctx.bankFeedAvailable) missing.push("bank_credits feed (offline)")
  if (type === "MISSING_SETTLEMENT") conflicts.push("captured payment has no settlement row")
  if (type === "SETTLEMENT_UNDER_CREDIT")
    conflicts.push(`expected ${money(dv.expected_settlement)} vs actual ${money(dv.actual_settlement)}`)

  const evidenceComplete = missing.length === 0
  const base = BASE_CONFIDENCE[type]
  let confidence = base
  let classification: Classification = "EXCEPTION"
  if (!evidenceComplete) {
    confidence = Math.min(base, DEGRADED_CAP)
    classification = "NEEDS_HUMAN_REVIEW"
  }

  const age = ageHours(p.ts)
  const ageFactor = 1 + Math.min(age, 96) / 96
  const priority = Math.round(Math.abs(amountAtRisk) * (confidence / 100) * ageFactor * SEVERITY[type])
  const tier = classification === "NEEDS_HUMAN_REVIEW" ? "MEDIUM" : tierFor(priority)

  const packet: EvidencePacket = {
    order: ctx.order ?? null,
    payment: p,
    refunds: (dataset.refunds ?? []).filter((r) => r.payment_id === p.payment_id),
    fees: (dataset.fees ?? []).filter((f) => f.payment_id === p.payment_id),
    settlement: ctx.settlement ?? null,
    bank_credit: ctx.bankFeedAvailable ? (ctx.credit ?? null) : null,
    derived_values: dv,
    conflicts,
    missing_evidence: missing,
    evidence_complete: evidenceComplete,
  }

  const c: Case = {
    case_id: "CF-" + p.payment_id.replace("pay_", "").replace("_d", "D").toUpperCase(),
    payment_id: p.payment_id,
    order_id: p.order_id,
    type,
    title: TITLES[type],
    classification,
    amount_at_risk: round2(Math.abs(amountAtRisk)),
    base_confidence: base,
    confidence,
    age_hours: age,
    priority_score: priority,
    tier,
    method: p.method,
    evidence_packet: packet,
    evidence_items: evidenceItems(type, p, ctx, dv),
    chain: buildChain(type, p, ctx, dv),
    investigation: null,
  }
  c.investigation = buildInvestigation(c)
  return c
}

function ev(source: string, label: string, value: string, status: EvidenceItem["status"]): EvidenceItem {
  return { source, label, value, status }
}

function evidenceItems(type: AnomalyType, p: Payment, ctx: Ctx, dv: DerivedValues): EvidenceItem[] {
  const items: EvidenceItem[] = [
    ev("payments", "Gross payment", money(dv.gross_payment), "ok"),
    ev("refunds", "Refund total", money(dv.refund_total), "ok"),
    ev("fees", "Fees + tax", money(dv.fee_total), "ok"),
    ev("engine", "Expected settlement", money(dv.expected_settlement), "ok"),
  ]
  if (type === "MISSING_SETTLEMENT") {
    items.push(ev("settlements", "Settlement row", "none found", "missing"))
  } else {
    items.push(
      ev(
        "settlements",
        "Actual settlement",
        money(dv.actual_settlement),
        Math.abs(dv.unexplained_gap) > 1 ? "broken" : "ok",
      ),
    )
    items.push(
      ctx.bankFeedAvailable
        ? ev(
            "bank_credits",
            "Bank credit",
            type === "MISSING_BANK_CREDIT" ? "none found" : money(dv.bank_credit_amount),
            type === "MISSING_BANK_CREDIT" ? "missing" : "ok",
          )
        : ev("bank_credits", "Bank credit feed", "OFFLINE — cannot confirm", "missing"),
    )
  }
  if (Math.abs(dv.unexplained_gap) > 1)
    items.push(ev("engine", "Unexplained gap", money(dv.unexplained_gap), "broken"))
  if (type === "DUPLICATE_PAYMENT")
    items.push(ev("payments", "Excess exposure", money(p.amount), "broken"))
  return items
}

function buildChain(type: AnomalyType, p: Payment, ctx: Ctx, dv: DerivedValues): ChainNode[] {
  const brokenAt: Record<AnomalyType, string> = {
    STATUS_MISMATCH: "ORDER",
    DUPLICATE_PAYMENT: "PAYMENT",
    REFUND_EXCEEDS_PAYMENT: "REFUND",
    MISSING_SETTLEMENT: "SETTLEMENT",
    SETTLEMENT_UNDER_CREDIT: "SETTLEMENT",
    MISSING_BANK_CREDIT: "BANK_CREDIT",
  }
  const b = brokenAt[type]
  const s = (stage: string): EvidenceItem["status"] =>
    stage === b ? "broken" : "ok"
  return [
    { stage: "ORDER", id: ctx.order?.order_id ?? p.order_id, label: "Order", value: ctx.order ? `${money(ctx.order.amount)} · ${ctx.order.status}` : "—", status: type === "STATUS_MISMATCH" ? "broken" : "ok" },
    { stage: "PAYMENT", id: p.payment_id, label: "Payment", value: `${money(p.amount)} · ${p.status}`, status: s("PAYMENT") },
    { stage: "REFUND", id: "—", label: "Refund", value: dv.refund_total ? money(dv.refund_total) : "none", status: s("REFUND") },
    { stage: "FEE", id: "—", label: "Fee", value: money(dv.fee_total), status: "ok" },
    { stage: "SETTLEMENT", id: ctx.settlement?.settlement_id ?? "—", label: "Settlement", value: type === "MISSING_SETTLEMENT" ? "missing" : money(dv.actual_settlement), status: s("SETTLEMENT") },
    { stage: "BANK_CREDIT", id: ctx.credit?.credit_id ?? "—", label: "Bank credit", value: !ctx.bankFeedAvailable ? "feed offline" : type === "MISSING_BANK_CREDIT" ? "missing" : money(dv.bank_credit_amount), status: !ctx.bankFeedAvailable ? "missing" : s("BANK_CREDIT") },
  ]
}

// ── Summary + metrics ─────────────────────────────────────────────────────
export function summarize(dataset: Dataset, cases: Case[]): RunSummary {
  const totalOrders = dataset.orders.length
  const raisedOrders = new Set(cases.map((c) => c.order_id)).size
  const needs = cases.filter((c) => c.classification === "NEEDS_HUMAN_REVIEW").length
  const explained = totalOrders - raisedOrders
  return {
    records_processed: totalOrders,
    reconciled: explained,
    explained,
    exceptions: cases.filter((c) => c.classification === "EXCEPTION").length,
    needs_review: needs,
    potential_exposure: round2(cases.reduce((s, c) => s + c.amount_at_risk, 0)),
  }
}

export function computeMetrics(cases: Case[], groundTruth: GroundTruthEntry[]): Metrics {
  const t0 = performance.now()
  const gtKeys = new Set(groundTruth.map((g) => g.payment_id + "|" + g.type))
  const detected = new Set(cases.map((c) => c.payment_id + "|" + c.type))
  let tp = 0
  let fp = 0
  for (const k of detected) (gtKeys.has(k) ? (tp += 1) : (fp += 1))
  let fn = 0
  for (const k of gtKeys) if (!detected.has(k)) fn += 1
  const precision = tp / (tp + fp || 1)
  const recall = tp / (tp + fn || 1)
  const f1 = (2 * precision * recall) / (precision + recall || 1)
  return {
    precision,
    recall,
    f1,
    true_positives: tp,
    false_positives: fp,
    false_negatives: fn,
    records_processed: 0,
    anomalies_planted: gtKeys.size,
    anomalies_detected: detected.size,
    potential_exposure: round2(cases.reduce((s, c) => s + c.amount_at_risk, 0)),
    processing_time_ms: Math.round(performance.now() - t0),
  }
}
