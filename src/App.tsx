import { useEffect, useState } from "react"
import type { Case, Mode, AuditEntry, AuditRun, Metrics } from "./lib/types"
import { money } from "./lib/engine"
import { fetchAudit, fetchMetrics, approve as apiApprove, REQUIRE_BACKEND, type Source } from "./lib/api"
import { TierBadge, ConfidenceBadge, TypeTag, ClassificationBadge } from "./components/badges"
import { CaseDetail } from "./components/CaseDetail"
import { MetricsPanel } from "./components/MetricsPanel"

type View = "overview" | "exceptions" | "metrics"

export default function App() {
  const [mode, setMode] = useState<Mode>("normal")
  const [view, setView] = useState<View>("overview")
  const [selected, setSelected] = useState<string | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [run, setRun] = useState<AuditRun | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [source, setSource] = useState<Source>(REQUIRE_BACKEND ? "unavailable" : "offline")
  const [loading, setLoading] = useState(true)
  const [backendDown, setBackendDown] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setBackendDown(false)
    Promise.all([fetchAudit(mode), fetchMetrics(mode)])
      .then(([a, m]) => {
        if (cancelled) return
        setRun(a.run)
        setMetrics(m.metrics)
        setSource(a.source)
        setLoading(false)
      })
      .catch(() => {
        // REQUIRE_BACKEND is on and the API is unreachable — do not show dev data.
        if (cancelled) return
        setBackendDown(true)
        setSource("unavailable")
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [mode])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null)
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const cases = run?.cases ?? []
  const summary = run?.summary
  const selectedCase = cases.find((c) => c.case_id === selected) ?? null

  // Returns true only when the backend created the authoritative audit entry.
  // In judging mode (REQUIRE_BACKEND) a backend failure throws — we never
  // fabricate a local approval — and the caller surfaces the failure.
  async function onApprove(c: Case): Promise<boolean> {
    try {
      const { entry } = await apiApprove(c)
      setAudit((prev) => [...prev, entry])
      return true
    } catch {
      return false
    }
  }

  return (
    <div className="flex h-full overflow-hidden bg-background text-foreground">
      {/* ── Left rail ─────────────────────────────────────────── */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
        <div className="border-b border-border p-6">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 bg-signal" />
            <span className="font-mono text-sm font-700 tracking-widest">CASEFILE</span>
          </div>
          <p className="mt-2 font-mono text-[11px] leading-relaxed text-muted">
            The investigation layer after reconciliation. Not "what doesn&apos;t match" — "why, and
            what to do about it."
          </p>
        </div>

        <nav className="flex flex-col p-2">
          {(["overview", "exceptions", "metrics"] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => {
                setView(v)
                setSelected(null)
              }}
              className={`flex items-center justify-between px-4 py-2.5 text-left font-mono text-xs uppercase tracking-widest transition-colors ${
                view === v ? "bg-surface-2 text-signal" : "text-muted hover:text-foreground"
              }`}
            >
              {v}
              {v === "exceptions" && <span className="text-foreground/60">{cases.length}</span>}
            </button>
          ))}
        </nav>

        <div className="mt-auto space-y-4 border-t border-border p-4">
          <FailureToggle mode={mode} onChange={setMode} />
          <SourceIndicator source={source} />
          <div className="font-mono text-[10px] leading-relaxed text-muted">
            <div className="flex justify-between">
              <span>ENGINE</span>
              <span className="text-foreground/70">deterministic</span>
            </div>
            <div className="flex justify-between">
              <span>AI INVESTIGATION</span>
              <span className="text-ok">enabled</span>
            </div>
            <div className="flex justify-between">
              <span>FINANCIAL ACTIONS</span>
              <span className="text-review">human approval</span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main ──────────────────────────────────────────────── */}
      <div className="relative flex min-w-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto">
          {loading && (
            <div className="flex h-full items-center justify-center font-mono text-xs text-muted">
              <span className="text-signal">▮</span>&nbsp; Running audit…
            </div>
          )}

          {!loading && backendDown && (
            <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
              <span className="inline-block h-3 w-3 bg-critical" />
              <h1 className="font-mono text-lg font-800 uppercase tracking-widest text-critical">
                Backend offline
              </h1>
              <p className="max-w-md font-mono text-xs leading-relaxed text-muted">
                CONNECT THE CASEFILE API TO CONTINUE. REQUIRE_BACKEND is enabled, so no fabricated
                financial metrics are shown. Start the backend with{" "}
                <span className="text-foreground">uvicorn backend.main:app --port 8000</span>.
              </p>
            </div>
          )}

          {!loading && !backendDown && view === "overview" && summary && (
            <Overview
              summary={summary}
              mode={mode}
              topCases={cases.slice(0, 6)}
              onOpen={(id) => {
                setView("exceptions")
                setSelected(id)
              }}
            />
          )}

          {!loading && !backendDown && view === "exceptions" && (
            <ExceptionsView cases={cases} selected={selected} onSelect={setSelected} />
          )}

          {!loading && !backendDown && view === "metrics" && metrics && (
            <div className="p-8">
              <MetricsPanel m={metrics} mode={mode} />
            </div>
          )}
        </main>

        {selectedCase && (
          <div className="w-[38rem] shrink-0 overflow-hidden">
            <CaseDetail c={selectedCase} mode={mode} audit={audit} onApprove={onApprove} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  )
}

function SourceIndicator({ source }: { source: Source }) {
  const conf =
    source === "backend"
      ? { cls: "border-ok text-ok", dot: "bg-ok", label: "FastAPI" }
      : source === "unavailable"
        ? { cls: "border-critical text-critical", dot: "bg-critical", label: "backend offline" }
        : { cls: "border-border-strong text-muted", dot: "bg-muted", label: "offline dev mode" }
  return (
    <div className={`flex items-center justify-between border px-3 py-2 font-mono text-[10px] uppercase tracking-widest ${conf.cls}`}>
      <span>Data source</span>
      <span className="flex items-center gap-1.5">
        <span className={`inline-block h-1.5 w-1.5 ${conf.dot}`} />
        {conf.label}
      </span>
    </div>
  )
}

// ── Overview ───────────────────────────────────────────────────
function Overview({
  summary,
  mode,
  topCases,
  onOpen,
}: {
  summary: NonNullable<AuditRun["summary"]>
  mode: Mode
  topCases: Case[]
  onOpen: (id: string) => void
}) {
  return (
    <div className="p-8">
      <header className="mb-8 flex items-end justify-between gap-6">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-widest text-muted">
            Financial health · order → payment → refund → fee → settlement → bank credit
          </div>
          <h1 className="mt-2 text-4xl font-900 tracking-tight">Audit complete.</h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
            {(summary.canonical_transactions ?? summary.records_processed).toLocaleString("en-IN")}{" "}
            transactions walked link-by-link. {summary.explained.toLocaleString("en-IN")} fully
            explained, {summary.exceptions.toLocaleString("en-IN")} exceptions and{" "}
            {summary.needs_review.toLocaleString("en-IN")} needing human review — each with assembled
            evidence, a scored confidence, and one bounded action.
          </p>
          {summary.total_records ? (
            <p className="mt-2 font-mono text-[11px] text-muted">
              {summary.total_records.toLocaleString("en-IN")} linked records ·{" "}
              {Math.round(summary.records_per_second ?? 0).toLocaleString("en-IN")} records/sec ·
              reconciled in {Math.round(summary.reconciliation_ms ?? 0).toLocaleString("en-IN")} ms ·
              avg confidence {summary.average_confidence ?? 0}%
            </p>
          ) : null}
        </div>
        {mode === "failure" && (
          <span className="border border-review px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-review">
            ⚠ Bank feed offline
          </span>
        )}
      </header>

      <div className="grid grid-cols-2 border border-border lg:grid-cols-5">
        <HealthCell label="Processed" value={String(summary.records_processed)} />
        <HealthCell label="Explained" value={String(summary.explained)} tone="ok" />
        <HealthCell label="Exceptions" value={String(summary.exceptions)} tone="high" />
        <HealthCell label="Needs review" value={String(summary.needs_review)} tone={summary.needs_review ? "review" : "muted"} />
        <HealthCell label="Exposure" value={money(summary.potential_exposure)} accent />
      </div>

      <div className="mt-10">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-700 uppercase tracking-wider">Top exposure</h2>
          <span className="font-mono text-[11px] text-muted">priority-ranked</span>
        </div>
        <div className="border border-border">
          {topCases.map((c, i) => (
            <button
              key={c.case_id}
              onClick={() => onOpen(c.case_id)}
              className={`flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-surface ${i > 0 ? "border-t border-border" : ""}`}
            >
              <span className="w-16 shrink-0 font-mono text-xs text-signal">{c.case_id}</span>
              <TierBadge tier={c.tier} />
              <span className="flex-1 truncate text-sm font-500">{c.title}</span>
              <ClassificationBadge c={c.classification} />
              <ConfidenceBadge value={c.confidence} base={c.base_confidence} degraded={c.classification === "NEEDS_HUMAN_REVIEW"} />
              <span className="w-24 shrink-0 text-right font-mono text-sm font-700 text-signal">
                {money(c.amount_at_risk)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function HealthCell({
  label,
  value,
  tone = "foreground",
  accent,
}: {
  label: string
  value: string
  tone?: "foreground" | "ok" | "high" | "review" | "muted"
  accent?: boolean
}) {
  const color = accent
    ? "text-signal"
    : tone === "ok"
      ? "text-ok"
      : tone === "high"
        ? "text-high"
        : tone === "review"
          ? "text-review"
          : tone === "muted"
            ? "text-muted"
            : "text-foreground"
  return (
    <div className="border-r border-border p-5 last:border-r-0">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`mt-2 font-mono text-2xl font-800 ${color}`}>{value}</div>
    </div>
  )
}

// ── Exceptions list ────────────────────────────────────────────
function ExceptionsView({
  cases,
  selected,
  onSelect,
}: {
  cases: Case[]
  selected: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="p-8">
      <header className="mb-6">
        <h1 className="text-3xl font-800 tracking-tight">Cases</h1>
        <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-muted">
          {cases.length} open · priority-ranked · amount × confidence × age × severity
        </p>
      </header>

      <div className="grid grid-cols-[5rem_5rem_1fr_8rem_7rem_6rem_5rem] gap-2 border-b border-border-strong pb-2 font-mono text-[10px] uppercase tracking-widest text-muted">
        <span>Case</span>
        <span>Tier</span>
        <span>Title</span>
        <span>Classification</span>
        <span>Confidence</span>
        <span className="text-right">At risk</span>
        <span className="text-right">Score</span>
      </div>

      <div>
        {cases.map((c) => (
          <button
            key={c.case_id}
            onClick={() => onSelect(c.case_id)}
            className={`grid w-full grid-cols-[5rem_5rem_1fr_8rem_7rem_6rem_5rem] items-center gap-2 border-b border-border py-3 text-left transition-colors hover:bg-surface ${
              selected === c.case_id ? "bg-surface-2" : ""
            }`}
          >
            <span className="font-mono text-xs text-signal">{c.case_id}</span>
            <TierBadge tier={c.tier} />
            <span className="min-w-0">
              <span className="flex items-center gap-2">
                <span className="truncate text-sm font-500">{c.title}</span>
                <TypeTag type={c.type} />
              </span>
              <span className="font-mono text-[10px] text-muted">
                {c.payment_id} · {c.method} · {c.age_hours}h
              </span>
            </span>
            <ClassificationBadge c={c.classification} />
            <ConfidenceBadge value={c.confidence} base={c.base_confidence} degraded={c.classification === "NEEDS_HUMAN_REVIEW"} />
            <span className="text-right font-mono text-sm font-700 text-signal">{money(c.amount_at_risk)}</span>
            <span className="text-right font-mono text-xs text-muted">{c.priority_score.toLocaleString("en-IN")}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Failure toggle ─────────────────────────────────────────────
function FailureToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const failure = mode === "failure"
  return (
    <div className="border border-border p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted">Failure simulation</div>
      <button
        onClick={() => onChange(failure ? "normal" : "failure")}
        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 font-mono text-[11px] transition-colors ${
          failure ? "border-review text-review" : "border-border-strong text-foreground hover:border-signal hover:text-signal"
        }`}
      >
        <span>{failure ? "Bank feed OFFLINE" : "Simulate bank feed offline"}</span>
        <span className={`inline-block h-3 w-6 border ${failure ? "border-review bg-review/30" : "border-border-strong"}`}>
          <span className={`block h-full w-3 transition-transform ${failure ? "translate-x-3 bg-review" : "bg-muted"}`} />
        </span>
      </button>
      <p className="mt-2 font-mono text-[10px] leading-relaxed text-muted">
        Re-runs the audit with bank-credit evidence removed. Confidence falls, status flips to review.
      </p>
    </div>
  )
}
