import type {
  Dataset,
  GroundTruthEntry,
  Order,
  Payment,
  Refund,
  Fee,
  Settlement,
  BankCredit,
  AnomalyType,
} from "./types"

/**
 * OFFLINE FALLBACK dataset. This mirrors the authoritative backend generator
 * (backend/data/generate_dataset.py) so the browser can render a coherent
 * preview when the FastAPI backend is unreachable. The backend is the source
 * of truth; this is deterministic and structurally identical.
 */
function mulberry32(seed: number) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const METHODS = ["upi", "card", "netbanking", "wallet"]
const BASE_TS = Date.parse("2026-08-26T09:00:00Z")
const round2 = (n: number) => Math.round(n * 100) / 100
const pad = (n: number, len = 4) => String(n).padStart(len, "0")

export interface GeneratedBatch {
  dataset: Dataset
  groundTruth: GroundTruthEntry[]
}

export function generateBatch(seed = 42): GeneratedBatch {
  const rand = mulberry32(seed)
  const N = 160

  const orders: Order[] = []
  const payments: Payment[] = []
  const refunds: Refund[] = []
  const fees: Fee[] = []
  const settlements: Settlement[] = []
  const bankCredits: BankCredit[] = []
  const groundTruth: GroundTruthEntry[] = []

  // Planted anomalies at fixed indices, spread across all 6 types.
  const plant: Record<number, AnomalyType> = {
    1: "SETTLEMENT_UNDER_CREDIT", // HERO case
    12: "SETTLEMENT_UNDER_CREDIT",
    88: "SETTLEMENT_UNDER_CREDIT",
    7: "DUPLICATE_PAYMENT",
    54: "DUPLICATE_PAYMENT",
    120: "DUPLICATE_PAYMENT",
    23: "MISSING_SETTLEMENT",
    77: "MISSING_SETTLEMENT",
    9: "REFUND_EXCEEDS_PAYMENT",
    140: "REFUND_EXCEEDS_PAYMENT",
    31: "STATUS_MISMATCH",
    99: "STATUS_MISMATCH",
    45: "MISSING_BANK_CREDIT",
    108: "MISSING_BANK_CREDIT",
    150: "MISSING_BANK_CREDIT",
  }

  let feeSeq = 1
  let refundSeq = 1
  let settleSeq = 1
  let creditSeq = 1

  for (let i = 0; i < N; i++) {
    const anomaly = plant[i]
    const hero = i === 1
    const orderId = "ord_" + pad(i + 1)
    const payId = "pay_" + pad(i + 1)
    const method = METHODS[Math.floor(rand() * METHODS.length)]
    const amount = hero ? 20000 : Math.round((800 + rand() * 24000) / 10) * 10
    const ts = new Date(BASE_TS + i * 21 * 60_000).toISOString()

    if (anomaly === "STATUS_MISMATCH") {
      orders.push({ order_id: orderId, amount, status: "created" })
      payments.push({ payment_id: payId, order_id: orderId, amount, status: "captured", method, ts })
      groundTruth.push({ payment_id: payId, type: anomaly })
    } else {
      orders.push({ order_id: orderId, amount, status: "paid" })
      payments.push({ payment_id: payId, order_id: orderId, amount, status: "captured", method, ts })
    }

    if (anomaly === "DUPLICATE_PAYMENT") {
      payments.push({
        payment_id: payId + "_d",
        order_id: orderId,
        amount,
        status: "captured",
        method,
        ts: new Date(BASE_TS + i * 21 * 60_000 + 90_000).toISOString(),
      })
      groundTruth.push({ payment_id: payId, type: anomaly })
    }

    // Fees.
    const feeAmt = hero ? 500 : round2(amount * 0.02)
    const taxAmt = hero ? 80 : round2(feeAmt * 0.18)
    fees.push({ fee_id: "fee_" + pad(feeSeq++), payment_id: payId, fee_amt: feeAmt, tax_amt: taxAmt })

    // Refunds — hero has a legit ₹1,000; over-refund anomaly exceeds payment.
    let refundTotal = 0
    const wantRefund = hero || anomaly === "REFUND_EXCEEDS_PAYMENT" || rand() < 0.16
    if (wantRefund) {
      const refundAmt = hero
        ? 1000
        : anomaly === "REFUND_EXCEEDS_PAYMENT"
          ? Math.round(amount * (1.15 + rand() * 0.4))
          : Math.round(amount * (0.15 + rand() * 0.35))
      refundTotal = refundAmt
      refunds.push({
        refund_id: "rfnd_" + pad(refundSeq++),
        payment_id: payId,
        amount: refundAmt,
        ts: new Date(BASE_TS + i * 21 * 60_000 + 3600_000).toISOString(),
      })
      if (anomaly === "REFUND_EXCEEDS_PAYMENT") groundTruth.push({ payment_id: payId, type: anomaly })
    }

    const feeTotal = round2(feeAmt + taxAmt)
    const expected = round2(amount - refundTotal - feeTotal)

    if (anomaly === "MISSING_SETTLEMENT") {
      groundTruth.push({ payment_id: payId, type: anomaly })
      continue
    }

    // Under-credit: actual settlement short of expected by an unexplained gap.
    const gap = hero ? 2000 : anomaly === "SETTLEMENT_UNDER_CREDIT" ? Math.round((expected * 0.1) / 10) * 10 : 0
    const actual = round2(expected - gap)
    if (anomaly === "SETTLEMENT_UNDER_CREDIT") groundTruth.push({ payment_id: payId, type: anomaly })

    const settleId = "setl_" + pad(settleSeq++)
    settlements.push({
      settlement_id: settleId,
      payment_id: payId,
      expected_amt: expected,
      actual_amt: actual,
      status: "settled",
      ts: new Date(BASE_TS + i * 21 * 60_000 + 2 * 3600_000).toISOString(),
    })

    if (anomaly === "MISSING_BANK_CREDIT") {
      groundTruth.push({ payment_id: payId, type: anomaly })
      continue
    }

    bankCredits.push({
      credit_id: "cr_" + pad(creditSeq++),
      settlement_id: settleId,
      amount: actual,
      ts: new Date(BASE_TS + i * 21 * 60_000 + 5 * 3600_000).toISOString(),
    })
  }

  return {
    dataset: { orders, payments, refunds, fees, settlements, bank_credits: bankCredits },
    groundTruth,
  }
}

export function rowCount(d: Dataset): number {
  return (
    d.orders.length +
    d.payments.length +
    d.refunds.length +
    d.fees.length +
    d.settlements.length +
    d.bank_credits.length
  )
}
