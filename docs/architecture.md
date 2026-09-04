# CaseFile — Architecture

## Data flow

```
React/Vite ──HTTP──▶ FastAPI ──▶ Python/pandas engine ──▶ evidence packet ──▶ AI provider (Gemini/OpenAI/Claude) ──▶ Case ──▶ Human approval ──▶ Audit trail
```

The browser is **not** the source of truth. Every financial value (exposure, confidence, priority,
precision/recall/F1, discrepancies) is computed in Python and displayed by the frontend.

## Backend (`backend/`)

| Module | Responsibility |
|---|---|
| `data/generate.py` | Deterministic, configurable generator. Builds N canonical transactions (default 100K) → 6 linked CSVs + `ground_truth.json` + `dataset_meta.json`. `generate_dataset.py` delegates to it. |
| `engine/loader.py` | The **only** pandas file — reads CSVs → plain records at the boundary. |
| `engine/chain_walker.py` | Walks Order→Payment→Refund→Fee→Settlement→Bank-credit per payment. |
| `engine/rules.py` | The anomaly rules (pure logic, no pandas, no LLM). |
| `engine/evidence.py` | Assembles the structured evidence packet + derived values. |
| `engine/scoring.py` | Deterministic confidence + priority + tier. |
| `engine/classification.py` | EXPLAINED / EXCEPTION / NEEDS_HUMAN_REVIEW / CONFLICTING_EVIDENCE. |
| `engine/failure_sim.py` | Drops the bank-credit feed and re-runs. |
| `engine/metrics.py` | Precision/recall/F1 vs. `ground_truth.json` (evaluation-only). |
| `llm/` | Provider-agnostic AI layer (`providers.py`: Gemini default, OpenAI, optional Claude; selected via `AI_PROVIDER`, only the chosen provider's SDK/key needed), the one locked prompt, Pydantic-validated structured output, retry. No silent fallback — see below. |
| `models/schemas.py` | Pydantic contract. |
| `audit/audit_log.py` | In-memory append-only audit trail. |
| `api/` | Routes (see contract below). |

**The engine never reads `ground_truth.json`.** Only `metrics` does, for evaluation.

## Boundaries that make it defensible

1. **Arithmetic is Python's job.** The LLM receives computed numbers and reasons about them; it never
   calculates or invents a figure, and never sets confidence.
2. **Confidence is deterministic** = base(type) + evidence-completeness − conflict penalty, capped at
   `MISSING_EVIDENCE_CAP = 54` when a required source is missing.
3. **AI has no financial authority.** Allowed: investigate / classify / draft / recommend. Human
   approval required for refund / payout / correction. Approve creates a draft; it moves no money.
4. **No silent fallback.** If the selected provider is unavailable or returns invalid JSON, the
   backend retries once. Under `REQUIRE_AI=true` it then returns an explicit *AI INVESTIGATION
   UNAVAILABLE* result — it never dresses deterministic text up as a provider's output. The
   deterministic path is reached only when `AI_PROVIDER=deterministic` (alias `fallback`) or
   `ALLOW_AI_FALLBACK=true`, and its output is always labelled `generated_by="fallback"`.

## API contract

```
GET  /api/health                               → { status }
GET  /api/readiness                            → { ready, canonical_transactions, total_records, ... }
POST /api/audit/run?mode=normal|failure        → { mode, summary, cases[] }   (cases bounded to top N)
GET  /api/cases?mode=&page=&page_size=         → { total, page, page_size, items[] }  (paginated)
GET  /api/cases/{case_id}?mode=                → Case
POST /api/cases/{case_id}/investigate?mode=    → Investigation (gemini | openai | claude | fallback | unavailable)
POST /api/cases/{case_id}/approve              → { audit_entry }
POST /api/failure-mode/bank-feed  {offline}    → { bank_feed_offline, mode, summary }
GET  /api/metrics?mode=                        → Metrics (+ measured benchmark fields)
GET  /api/audit-log                            → AuditEntry[]
```

The full case set (thousands on a 100K run) is never shipped to the browser at once: `audit/run`
returns the summary plus the top `MAX_CASES_RETURNED` priority-ranked cases, and the complete list
is available through the paginated `/api/cases`.

## Frontend (`src/`)

`lib/api.ts` is backend-first with a deterministic offline fallback (`lib/engine.ts`,
`lib/dataset.ts`, `lib/narrative.ts`) that mirrors the same contract so the hosted preview renders
without a backend. The sidebar surfaces which source is live. The Case Detail screen is the centre
of gravity: classification, exposure, confidence, evidence completeness, the transaction chain with
the broken link highlighted, and the FACT / HYPOTHESIS / RECOMMENDATION investigation.
