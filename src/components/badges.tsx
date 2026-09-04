import type { Tier, AnomalyType, Classification } from "../lib/types"

const TIER_COLOR: Record<Tier, string> = {
  CRITICAL: "text-critical border-critical",
  HIGH: "text-high border-high",
  MEDIUM: "text-medium border-medium",
  LOW: "text-low border-low",
}

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span
      className={`inline-flex items-center border px-1.5 py-0.5 font-mono text-[10px] font-600 uppercase tracking-widest ${TIER_COLOR[tier]}`}
    >
      {tier}
    </span>
  )
}

const CLASS_COLOR: Record<Classification, string> = {
  EXPLAINED: "text-ok border-ok",
  EXCEPTION: "text-high border-high",
  NEEDS_HUMAN_REVIEW: "text-review border-review",
  CONFLICTING_EVIDENCE: "text-critical border-critical",
}

export function ClassificationBadge({ c }: { c: Classification }) {
  return (
    <span
      className={`inline-flex items-center border px-2 py-0.5 font-mono text-[10px] font-600 uppercase tracking-widest ${CLASS_COLOR[c]}`}
    >
      {c.replace(/_/g, " ")}
    </span>
  )
}

export function ConfidenceBadge({
  value,
  base,
  degraded,
}: {
  value: number
  base?: number
  degraded?: boolean
}) {
  const color = degraded
    ? "text-review border-review"
    : value >= 90
      ? "text-ok border-ok"
      : value >= 70
        ? "text-medium border-medium"
        : "text-high border-high"
  return (
    <span className={`inline-flex items-baseline gap-1 border px-2 py-0.5 font-mono text-xs ${color}`}>
      <span className="font-700">{value}%</span>
      {degraded && base != null && (
        <span className="text-[10px] text-muted line-through decoration-1">{base}%</span>
      )}
    </span>
  )
}

const TYPE_LABEL: Record<AnomalyType, string> = {
  DUPLICATE_PAYMENT: "DUPLICATE",
  MISSING_SETTLEMENT: "NO SETTLE",
  REFUND_EXCEEDS_PAYMENT: "OVER-REFUND",
  STATUS_MISMATCH: "STATUS",
  MISSING_BANK_CREDIT: "NO CREDIT",
  SETTLEMENT_UNDER_CREDIT: "UNDER-CREDIT",
}

export function TypeTag({ type }: { type: AnomalyType }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">{TYPE_LABEL[type]}</span>
  )
}
