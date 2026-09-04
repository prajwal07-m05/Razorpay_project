import { useEffect, useState } from "react"
import type { Case, AuditEntry, Investigation, Mode, ChainNode } from "../lib/types"
import { money } from "../lib/engine"
import { investigate as apiInvestigate, BackendRequired } from "../lib/api"
import { ConfidenceBadge, TierBadge, TypeTag, ClassificationBadge } from "./badges"

export function CaseDetail({
  c,
  mode,
  audit,
  onApprove,
  onClose,
}: {
  c: Case
  mode: Mode
  audit: AuditEntry[]
  onApprove: (c: Case) => Promise<boolean>
  onClose: () => void
}) {
  const [approved, setApproved] = useState(false)
  const [approveError, setApproveError] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const [investigating, setInvestigating] = useState(false)

  // "backend-offline": the /investigate request itself failed under REQUIRE_BACKEND
  // (no AI result at all). "unavailable": backend answered but the configured
  // AI provider was unreachable (generated_by=unavailable). These are surfaced differently.
  const [source, setSource] = useState<"backend" | "fallback" | "unavailable" | "backend-offline">("fallback")

  // The real provider that produced a live result (gemini | openai | claude).
  const [provider, setProvider] = useState<string>("")

  const degraded = c.classification === "NEEDS_HUMAN_REVIEW"
  const caseAudit = audit.filter((a) => a.case_id === c.case_id)

  // Reset per-case state and auto-run the AI investigation on open.
  useEffect(() => {
    setInvestigation(null)
    setApproved(caseAudit.some((a) => a.action === "HUMAN_APPROVAL"))
    setApproveError(null)

    let cancelled = false

    setInvestigating(true)

    apiInvestigate(c, mode)
      .then(({ investigation }) => {
        if (cancelled) return

        setInvestigation(investigation)

        const g = investigation.generated_by
        const live = g === "gemini" || g === "openai" || g === "claude"

        setProvider(live ? g : "")
        setSource(live ? "backend" : g === "unavailable" ? "unavailable" : "fallback")
      })
      .catch((e) => {
        if (cancelled) return

        // Judging mode: the backend was unreachable. Do NOT show the local
        // deterministic investigation — surface an explicit unavailable state.
        setInvestigation(null)
        setSource(e instanceof BackendRequired ? "backend-offline" : "unavailable")
      })
      .finally(() => !cancelled && setInvestigating(false))

    return () => {
      cancelled = true
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.case_id, mode])

  const dv = c.evidence_packet.derived_values

  return (
    <div className="flex h-full flex-col border-l border-border bg-surface">
      <div className="flex items-start justify-between gap-4 border-b border-border p-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-signal">{c.case_id}</span>
            <TypeTag type={c.type} />
            <ClassificationBadge c={c.classification} />
            <TierBadge tier={c.tier} />
          </div>

          <h2 className="mt-2 text-2xl font-800 leading-tight tracking-tight">{c.title}</h2>

          <div className="mt-1 font-mono text-xs text-muted">
            {c.payment_id} · {c.order_id} · {c.method} · {c.age_hours}h old
          </div>
        </div>

        <button
          onClick={onClose}
          className="border border-border px-2 py-1 font-mono text-xs text-muted transition-colors hover:border-border-strong hover:text-foreground"
        >
          ESC
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="grid grid-cols-4 border-b border-border">
          <Stat label="Exposure" value={money(c.amount_at_risk)} accent />

          <Stat
            label="Confidence"
            node={<ConfidenceBadge value={c.confidence} base={c.base_confidence} degraded={degraded} />}
          />

          <Stat
            label="Evidence"
            node={
              <span
                className={`font-mono text-xs ${
                  c.evidence_packet.evidence_complete ? "text-ok" : "text-review"
                }`}
              >
                {c.evidence_packet.evidence_complete ? "COMPLETE" : "INCOMPLETE"}
              </span>
            }
          />

          <Stat label="Priority" value={c.priority_score.toLocaleString("en-IN")} />
        </div>

        {/* Transaction chain */}
        <Section
          title="Transaction chain"
          sub="Order → Payment → Refund → Fee → Settlement → Bank credit"
        >
          <div className="space-y-0">
            {c.chain.map((n, i) => (
              <ChainRow key={n.stage} node={n} last={i === c.chain.length - 1} />
            ))}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-px border border-border bg-border">
            <Derived label="Expected" value={money(dv.expected_settlement)} />

            <Derived label="Actual" value={money(dv.actual_settlement)} />

            <Derived
              label="Unexplained gap"
              value={money(dv.unexplained_gap)}
              broken={Math.abs(dv.unexplained_gap) > 1}
            />
          </div>
        </Section>

        {/* Evidence */}
        <Section
          title="Evidence packet"
          sub="Structured facts — assembled by the deterministic engine, zero LLM"
        >
          <div className="border border-border">
            {c.evidence_items.map((e, i) => (
              <div
                key={i}
                className={`flex items-center justify-between gap-4 px-4 py-2.5 font-mono text-xs ${
                  i > 0 ? "border-t border-border" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={`inline-block h-1.5 w-1.5 ${dot(e.status)}`} />
                  <span className="uppercase tracking-wider text-muted">{e.source}</span>
                  <span className="text-foreground/70">{e.label}</span>
                </div>

                <span className="text-foreground">{e.value}</span>
              </div>
            ))}
          </div>

          {c.evidence_packet.missing_evidence.length > 0 && (
            <p className="mt-2 font-mono text-[11px] text-review">
              Missing: {c.evidence_packet.missing_evidence.join(", ")}
            </p>
          )}
        </Section>

        {/* AI investigation */}
        <Section
          title="AI investigator"
          sub={
            source === "backend"
              ? `Live ${provider.toUpperCase()} call · evidence JSON in → reasoning out · never computes numbers`
              : source === "backend-offline"
                ? "AI investigation unavailable · the CaseFile backend is unreachable"
                : source === "unavailable"
                  ? "AI investigation unavailable · configured AI provider was unreachable"
                  : "DETERMINISTIC FALLBACK · configured AI provider not reachable · rule-based reasoning, not AI"
          }
        >
          {source === "fallback" && !investigating && (
            <div className="mb-4 border border-medium/40 bg-medium/5 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-medium">
              ⚠ Deterministic fallback — not an AI provider result
            </div>
          )}

          {source === "backend-offline" && !investigating && (
            <div className="mb-4 border border-critical/40 bg-critical/5 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-critical">
              AI investigation unavailable — backend offline
            </div>
          )}

          {source === "unavailable" && !investigating && (
            <div className="mb-4 border border-critical/40 bg-critical/5 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-critical">
              AI investigation unavailable
            </div>
          )}

          {investigating && (
            <div className="border border-border p-4 font-mono text-xs text-muted">
              <span className="text-signal">▮</span> Investigating evidence packet…
            </div>
          )}

          {!investigating && investigation && (
            <div className="space-y-5">
              <p className="text-sm leading-relaxed text-foreground/90">{investigation.summary}</p>

              <Block label="Facts">
                <ul className="space-y-1.5">
                  {investigation.facts.map((f, i) => (
                    <li
                      key={i}
                      className="grid grid-cols-[auto_1fr] gap-2 text-sm leading-relaxed text-foreground/90"
                    >
                      <span className="font-mono text-[10px] text-ok">FACT</span>
                      <span>{stripLabel(f)}</span>
                    </li>
                  ))}
                </ul>
              </Block>

              <Block label="Root-cause hypothesis">
                <p className="text-sm leading-relaxed text-foreground/90">
                  <span className="mr-2 font-mono text-[10px] text-medium">HYPOTHESIS</span>
                  {stripLabel(investigation.root_cause_hypothesis)}
                </p>
              </Block>

              {investigation.alternative_explanations.length > 0 && (
                <Block label="Alternative explanations">
                  <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed text-muted">
                    {investigation.alternative_explanations.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </Block>
              )}

              <Block label="Contradictory evidence">
                <ul className="space-y-1 text-sm leading-relaxed text-muted">
                  {investigation.contradictory_evidence.map((a, i) => (
                    <li key={i}>— {a}</li>
                  ))}
                </ul>
              </Block>

              <div className="grid grid-cols-[auto_1fr] gap-3 border border-border p-4">
                <span className="font-mono text-[10px] text-signal">REC</span>

                <div>
                  <div className="font-mono text-[10px] uppercase tracking-widest text-muted">
                    Recommended action · sufficiency {investigation.evidence_sufficiency}
                  </div>

                  <p className="mt-1 text-sm leading-relaxed text-foreground/90">
                    {stripLabel(investigation.recommended_action)}
                  </p>
                </div>
              </div>
            </div>
          )}
        </Section>

        {/* Action + audit */}
        <Section
          title="Human-in-the-loop"
          sub="AI investigation ENABLED · financial actions HUMAN APPROVAL REQUIRED"
        >
          <div className="border border-border p-4">
            <button
              disabled={approved || degraded || approving}
              onClick={async () => {
                setApproving(true)
                setApproveError(null)

                const ok = await onApprove(c)

                setApproving(false)

                if (ok) setApproved(true)
                else setApproveError("APPROVAL FAILED — BACKEND UNAVAILABLE")
              }}
              className={`w-full border px-4 py-3 font-mono text-sm font-600 uppercase tracking-widest transition-colors ${
                degraded
                  ? "cursor-not-allowed border-border text-muted"
                  : approved
                    ? "border-ok text-ok"
                    : "border-signal bg-signal text-signal-fg hover:bg-transparent hover:text-signal"
              }`}
            >
              {degraded
                ? "Blocked — needs human review"
                : approving
                  ? "Submitting to backend…"
                  : approved
                    ? "✓ Draft created — no money moved"
                    : "Approve recommended action (draft only)"}
            </button>

            {approveError && (
              <p className="mt-3 border border-critical/40 bg-critical/5 px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-critical">
                {approveError}
              </p>
            )}

            <p className="mt-3 font-mono text-[11px] leading-relaxed text-muted">
              {degraded
                ? "Degraded to review — a required evidence source is offline. Approval is disabled by design."
                : "Approve logs the decision and creates a draft. It never issues a refund, payout, or correction."}
            </p>
          </div>

          {caseAudit.length > 0 && (
            <div className="mt-4 border border-border">
              <div className="border-b border-border px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-muted">
                Audit trail
              </div>

              {caseAudit.map((a, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between gap-3 px-4 py-2 font-mono text-[11px]"
                >
                  <span className="text-muted">
                    {new Date(a.timestamp).toLocaleTimeString("en-IN")}
                  </span>

                  <span className="text-signal">{a.action}</span>

                  <span className="flex-1 text-right text-foreground/70">{a.result}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}

// Strip a leading role label (e.g. "HYPOTHESIS:") so it doesn't double up with
// the label the UI already renders. Handles both fallback text and live provider output.
function stripLabel(s: string) {
  return s.replace(/^\s*(FACT|HYPOTHESIS|HYP|RECOMMENDATION|REC)\s*:\s*/i, "")
}

function dot(status: ChainNode["status"]) {
  return status === "ok" ? "bg-ok" : status === "missing" ? "bg-review" : "bg-critical"
}

function ChainRow({ node, last }: { node: ChainNode; last: boolean }) {
  const broken = node.status !== "ok"

  return (
    <div className="relative pl-6">
      <span className={`absolute left-1 top-1.5 inline-block h-2 w-2 ${dot(node.status)}`} />

      {!last && <span className="absolute left-[7px] top-3.5 h-full w-px bg-border" />}

      <div
        className={`flex items-center justify-between gap-4 border-b border-border py-2 ${
          broken ? "bg-critical/5" : ""
        }`}
      >
        <div className="flex items-baseline gap-3">
          <span
            className={`font-mono text-[10px] uppercase tracking-widest ${
              broken ? "text-critical" : "text-muted"
            }`}
          >
            {node.label}
          </span>

          <span className="font-mono text-[10px] text-muted/60">{node.id}</span>
        </div>

        <span
          className={`font-mono text-xs ${
            broken ? "font-700 text-critical" : "text-foreground"
          }`}
        >
          {node.value}
        </span>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  node,
  accent,
}: {
  label: string
  value?: string
  node?: React.ReactNode
  accent?: boolean
}) {
  return (
    <div className="border-r border-border px-4 py-4 last:border-r-0">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</div>

      <div
        className={`mt-1 font-mono text-sm font-700 ${
          accent ? "text-signal" : "text-foreground"
        }`}
      >
        {node ?? value}
      </div>
    </div>
  )
}

function Derived({
  label,
  value,
  broken,
}: {
  label: string
  value: string
  broken?: boolean
}) {
  return (
    <div className="bg-surface px-4 py-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</div>

      <div
        className={`mt-1 font-mono text-sm font-700 ${
          broken ? "text-critical" : "text-foreground"
        }`}
      >
        {value}
      </div>
    </div>
  )
}

function Section({
  title,
  sub,
  children,
}: {
  title: string
  sub: string
  children: React.ReactNode
}) {
  return (
    <div className="border-b border-border p-6">
      <h3 className="text-sm font-700 uppercase tracking-wider">{title}</h3>

      <p className="mb-4 mt-0.5 font-mono text-[11px] text-muted">{sub}</p>

      {children}
    </div>
  )
}

function Block({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted">
        {label}
      </div>

      {children}
    </div>
  )
}
