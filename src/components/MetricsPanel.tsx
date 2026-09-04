import type { Metrics, Mode } from "../lib/types"
import { money } from "../lib/engine"

export function MetricsPanel({ m, mode }: { m: Metrics; mode: Mode }) {
  const pct = (n: number) => (n * 100).toFixed(1) + "%"
  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-8">
        <h2 className="text-3xl font-800 tracking-tight">Accuracy vs. hidden ground truth</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Computed by the engine against planted labels it never reads. Every number here is
          recomputed live from the run — a number, not a slide.
        </p>
      </header>

      <div className="grid grid-cols-3 border border-border">
        <BigStat label="Precision" value={pct(m.precision)} />
        <BigStat label="Recall" value={pct(m.recall)} />
        <BigStat label="F1 score" value={pct(m.f1)} accent />
      </div>

      <div className="mt-px grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
        <SmallStat label="Records processed" value={String(m.records_processed)} />
        <SmallStat label="Anomalies planted" value={String(m.anomalies_planted)} />
        <SmallStat label="Detected" value={String(m.anomalies_detected)} />
        <SmallStat label="Potential exposure" value={money(m.potential_exposure)} tone="signal" />
        <SmallStat label="True positives" value={String(m.true_positives)} tone="ok" />
        <SmallStat label="False positives" value={String(m.false_positives)} tone={m.false_positives ? "high" : "muted"} />
        <SmallStat label="False negatives" value={String(m.false_negatives)} tone={m.false_negatives ? "high" : "muted"} />
        <SmallStat label="True negatives" value={(m.true_negatives ?? 0).toLocaleString("en-IN")} tone="muted" />
      </div>

      {m.total_records ? (
        <div className="mt-8">
          <div className="mb-3 font-mono text-[11px] uppercase tracking-widest text-muted">
            Benchmark · measured on this run, not fabricated
          </div>
          <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
            <SmallStat label="Canonical txns" value={(m.canonical_transactions ?? 0).toLocaleString("en-IN")} />
            <SmallStat label="Linked records" value={m.total_records.toLocaleString("en-IN")} />
            <SmallStat label="Throughput" value={`${Math.round(m.records_per_second ?? 0).toLocaleString("en-IN")}/s`} tone="signal" />
            <SmallStat label="Reconciliation" value={`${Math.round(m.reconciliation_ms ?? 0).toLocaleString("en-IN")} ms`} />
            <SmallStat label="Generation" value={`${Math.round(m.generation_time_ms ?? 0).toLocaleString("en-IN")} ms`} tone="muted" />
            <SmallStat label="Load time" value={`${Math.round(m.loading_time_ms ?? 0).toLocaleString("en-IN")} ms`} tone="muted" />
            <SmallStat label="Unexplained exposure" value={money(m.unexplained_exposure ?? 0)} tone="high" />
            <SmallStat label="Avg confidence" value={`${m.average_confidence ?? 0}%`} tone="ok" />
          </div>
        </div>
      ) : null}

      <div className="mt-8 border border-border p-6">
        <div className="font-mono text-[10px] uppercase tracking-widest text-muted">Read-out</div>
        <p className="mt-2 text-sm leading-relaxed text-foreground/90">
          {mode === "failure" ? (
            <>
              Bank-credit feed is <span className="text-review">offline</span>. Settlement
              discrepancies can no longer be confirmed downstream, so those cases are held for human
              review rather than asserted — the engine degrades honestly instead of guessing.
            </>
          ) : (
            <>
              The engine caught <span className="text-ok">{m.true_positives}</span> planted anomalies
              with <span className="text-signal">{m.false_positives}</span> false positives and{" "}
              <span className="text-high">{m.false_negatives}</span> misses across{" "}
              {m.records_processed} transactions.
            </>
          )}
        </p>
      </div>
    </div>
  )
}

function BigStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border-r border-border px-6 py-8 last:border-r-0">
      <div className="font-mono text-[11px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`mt-2 font-mono text-4xl font-800 ${accent ? "text-signal" : "text-foreground"}`}>
        {value}
      </div>
    </div>
  )
}

function SmallStat({
  label,
  value,
  tone = "foreground",
}: {
  label: string
  value: string
  tone?: "foreground" | "ok" | "high" | "muted" | "signal"
}) {
  const color =
    tone === "ok"
      ? "text-ok"
      : tone === "high"
        ? "text-high"
        : tone === "signal"
          ? "text-signal"
          : tone === "muted"
            ? "text-muted"
            : "text-foreground"
  return (
    <div className="bg-surface px-5 py-5">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`mt-1 font-mono text-xl font-700 ${color}`}>{value}</div>
    </div>
  )
}
