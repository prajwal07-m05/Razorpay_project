import type { AuditRun, Case, Metrics, Investigation, AuditEntry, Mode } from "./types"
import { generateBatch } from "./dataset"
import { runAudit, summarize, computeMetrics } from "./engine"

/**
 * Backend-first client. The FastAPI backend is the authoritative source for
 * every financial value. When it is unreachable (e.g. the hosted preview has
 * no backend), we fall back to the deterministic in-browser engine, which
 * mirrors the same contract — and we surface that we are offline so the UI can
 * say so honestly. The offline path is a graceful degradation, never the
 * intended production path.
 */
// Default to same-origin ("") so requests hit /api/* and are forwarded by the
// Vite dev proxy to the backend (see vite.config.ts). Set VITE_API_BASE to call
// a backend on a different origin directly.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? ""

// When REQUIRE_BACKEND is true, we refuse to silently fall back to the offline
// in-browser dataset — a hard-offline state is surfaced instead, so the UI can
// tell the user to connect the CaseFile API rather than showing dev data.
export const REQUIRE_BACKEND =
  ((import.meta.env.VITE_REQUIRE_BACKEND as string | undefined) ?? "").toLowerCase() === "true"

export type Source = "backend" | "offline" | "unavailable"

let connected: boolean | null = null // null = unknown, true/false = last probe
export function lastSource(): Source {
  return connected ? "backend" : REQUIRE_BACKEND ? "unavailable" : "offline"
}

// Thrown when a backend request fails while REQUIRE_BACKEND is on. Callers use
// it to distinguish "backend unavailable" from a normal offline degradation and
// to surface an explicit error rather than substituting local data.
export class BackendRequired extends Error {}
function offlineOr<T>(fallback: () => T): { value: T; source: Source } {
  connected = false
  if (REQUIRE_BACKEND) throw new BackendRequired("backend required but unreachable")
  return { value: fallback(), source: "offline" }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 4000)
  try {
    const res = await fetch(API_BASE + path, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    connected = true
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

// ── Offline engine (deterministic mirror of the backend) ───────────────────
const batch = generateBatch()
function offlineRun(mode: Mode): AuditRun {
  const cases = runAudit(batch.dataset, mode)
  return { mode, summary: summarize(batch.dataset, cases), cases }
}
function offlineMetrics(mode: Mode): Metrics {
  const cases = runAudit(batch.dataset, mode)
  const m = computeMetrics(cases, batch.groundTruth)
  m.records_processed = batch.dataset.orders.length
  return m
}

// ── Public API ─────────────────────────────────────────────────────────────
export async function fetchAudit(mode: Mode): Promise<{ run: AuditRun; source: Source }> {
  try {
    const run = await req<AuditRun>(`/api/audit/run?mode=${mode}`, { method: "POST" })
    return { run, source: "backend" }
  } catch (e) {
    if (e instanceof BackendRequired) throw e
    const { value, source } = offlineOr(() => offlineRun(mode))
    return { run: value, source }
  }
}

export async function fetchMetrics(mode: Mode): Promise<{ metrics: Metrics; source: Source }> {
  try {
    const metrics = await req<Metrics>(`/api/metrics?mode=${mode}`)
    return { metrics, source: "backend" }
  } catch (e) {
    if (e instanceof BackendRequired) throw e
    const { value, source } = offlineOr(() => offlineMetrics(mode))
    return { metrics: value, source }
  }
}

export async function investigate(c: Case, mode: Mode): Promise<{ investigation: Investigation; source: Source }> {
  try {
    const investigation = await req<Investigation>(`/api/cases/${c.case_id}/investigate?mode=${mode}`, {
      method: "POST",
    })
    return { investigation, source: "backend" }
  } catch (e) {
    if (e instanceof BackendRequired) throw e
    // REQUIRE_BACKEND on → offlineOr throws BackendRequired (no local fallback).
    // REQUIRE_BACKEND off → dev-only: return the deterministic investigation
    // already assembled for this case, clearly labelled offline by the caller.
    const { value, source } = offlineOr(() => c.investigation!)
    return { investigation: value, source }
  }
}

export async function approve(c: Case): Promise<{ entry: AuditEntry; source: Source }> {
  const entry: AuditEntry = {
    timestamp: new Date().toISOString(),
    case_id: c.case_id,
    action: "HUMAN_APPROVAL",
    actor: "human@merchant",
    result: `Draft created for ${c.amount_at_risk} — no money moved`,
  }
  try {
    const res = await req<{ audit_entry: AuditEntry }>(`/api/cases/${c.case_id}/approve`, {
      method: "POST",
      body: JSON.stringify({ actor: "human@merchant" }),
    })
    return { entry: res.audit_entry, source: "backend" }
  } catch (e) {
    if (e instanceof BackendRequired) throw e
    // REQUIRE_BACKEND on → offlineOr throws BackendRequired: no local approval is
    // fabricated and the caller reports the failure. REQUIRE_BACKEND off → dev-only
    // local draft entry (offline development mode).
    const { value, source } = offlineOr(() => entry)
    return { entry: value, source }
  }
}
