# CaseFile


**Evidence-driven financial investigation controller for payment operations.**

**🚀 Live Demo:** https://casefile-wcn1.onrender.com

CaseFile is a backend-first financial investigation system that operates after deterministic reconciliation. It traces a transaction across:

`Order → Payment → Refund → Fee → Settlement → Bank Credit`

The system first establishes financial facts with deterministic Python rules. It then gives a structured evidence packet to an AI investigator for root-cause analysis and a bounded recommendation. AI cannot change financial values, confidence, priority, exposure, or execute financial actions.

## Problem

A reconciliation system can identify that records do not match. Operations teams still need to answer:

- Why did the mismatch happen?
- Is it a genuine exception or an explainable case?
- What evidence supports the conclusion?
- What evidence is missing or contradictory?
- How confident is the conclusion when evidence disappears?
- What should a human reviewer investigate next?

CaseFile addresses this investigation layer.

## What is different

CaseFile is **not a replacement for reconciliation** and does not claim to detect anomalies with an LLM.

| Conventional reconciliation | CaseFile |
|---|---|
| Detects mismatches | Investigates detected exceptions |
| Matches records | Builds a cross-source evidence packet |
| Produces flags | Classifies cases as `EXPLAINED`, `EXCEPTION`, or `NEEDS_HUMAN_REVIEW` |
| Treats available evidence as static | Recalculates confidence when evidence becomes unavailable |
| Human investigation happens outside the system | Investigation, recommendation, approval, and audit trail are connected |
| LLM may be used for text generation | LLM receives structured evidence only; Python remains authoritative |

The core design principle is:

> **Python establishes financial truth. AI investigates the evidence surrounding that truth.**

## System architecture

```text
                         CaseFile

  Orders / Payments / Refunds / Fees / Settlements / Bank Credits
                              |
                              v
                    Python Financial Engine
              loader → chain walker → rules → evidence
                              |
                              v
                    Deterministic Scoring
              exposure / confidence / priority / tier
                              |
                              v
                     Case Classification
        EXPLAINED / EXCEPTION / NEEDS_HUMAN_REVIEW
                              |
                              v
                    Structured Evidence Packet
          facts + derived values + missing evidence + conflicts
                              |
                              v
                    AI Investigation Service
                    /        |        \
               Gemini     OpenAI     Claude
                  \          |          /
                   +---------+---------+
                              |
                              v
                  Validated InvestigationResult
             facts / hypothesis / alternatives / action
                              |
                              v
                       Human Approval
                    draft only; no funds moved
                              |
                              v
                         Audit Trail
```

### Source-of-truth boundary

The browser is not authoritative.

The FastAPI backend owns the financial audit. The frontend requests calculated values from the backend in normal operation.

The Python engine is responsible for:

- transaction-chain traversal
- anomaly rules
- expected settlement calculation
- unexplained gap calculation
- amount at risk
- confidence
- priority score
- priority tier
- classification
- benchmark metrics

The AI investigator is responsible for:

- evidence interpretation
- root-cause hypothesis
- alternative explanations
- evidence sufficiency reasoning
- bounded recommendation

The AI provider is never allowed to become the financial source of truth.

## Evidence-sensitive investigation

CaseFile treats evidence availability as part of the decision.

For a settlement-under-credit case, the deterministic engine can establish:

```text
Payment             ₹20,000
Refund              ₹1,000
Fees                  ₹580
Expected settlement ₹18,420
Actual settlement   ₹16,420
Bank credit         ₹16,420
                    --------
Unexplained gap      ₹2,000
```

With complete evidence, the case can be classified as an `EXCEPTION` with the rule-derived confidence for the anomaly type.

When the bank feed is disabled, the backend removes bank-credit evidence and reruns the audit. Confidence is capped at `MISSING_EVIDENCE_CAP = 54`, and the case can become `NEEDS_HUMAN_REVIEW` because the available evidence is no longer sufficient to support the same conclusion.

This is a backend state change, not a frontend animation or hard-coded demo percentage.

## Case classification

### `EXPLAINED`

The available financial records account for the transaction without an unexplained discrepancy. These cases demonstrate that the system does not simply flag every unusual record.

### `EXCEPTION`

The required evidence is available and the deterministic engine identifies an unexplained financial inconsistency or rule violation.

### `NEEDS_HUMAN_REVIEW`

Required evidence is missing, so the system refuses to present a high-confidence conclusion that the available records cannot support.

### `CONFLICTING_EVIDENCE`

Sources contain contradictory information that requires review rather than an unsupported conclusion.

## Detection rules currently implemented

The backend contains deterministic rules for:

- missing settlement
- duplicate payment
- refund exceeding payment
- status mismatch
- missing bank credit
- settlement under-credit
- duplicate refund
- unverified settlement in failure-mode handling

These rules do not depend on an LLM.

## AI investigation contract

The AI receives a structured evidence packet containing the records and derived values already assembled by the financial engine.

The investigation schema contains:

- `summary`
- `facts`
- `root_cause_hypothesis`
- `alternative_explanations`
- `contradictory_evidence`
- `evidence_sufficiency`
- `recommended_action`
- `reasoning`
- `generated_by`

The investigator is expected to distinguish facts from hypotheses and identify evidence limitations.

The implementation validates the provider response against the Pydantic investigation schema.

### Provider abstraction

Supported providers:

- Gemini — default
- OpenAI
- Claude — optional
- Deterministic — explicit offline/development mode

The provider can be changed without changing the financial engine.

With `REQUIRE_AI=true`, a real-provider failure is surfaced as `AI INVESTIGATION UNAVAILABLE`. A configured provider is not silently replaced by deterministic output.

## Human-in-the-loop boundary

CaseFile does not authorize the AI to execute financial actions.

AI can:

- investigate
- explain
- classify
- recommend
- draft

Human approval is required for the workflow's approval step. The current approval endpoint records a human approval as **draft only; no funds moved**.

The system does not implement autonomous refunds, payouts, settlement changes, or other irreversible financial actions.

## Auditability

The backend records investigation lifecycle events including:

- evidence assembled
- AI investigation started
- AI investigation completed
- recommendation generated
- human approval

This creates an inspectable sequence from evidence to recommendation to human action.

## Dataset and benchmark

The reference dataset is deterministic and reproducible.

```text
Canonical transactions: 100,000
Total linked records:   530,238
Seed:                   42
Planted anomalies:      1,042
```

The six generated tables are:

- `orders.csv`
- `payments.csv`
- `refunds.csv`
- `fees.csv`
- `settlements.csv`
- `bank_credits.csv`

The dataset generator is configurable through `CASEFILE_DATASET_SIZE`, `CASEFILE_SEED`, and `CASEFILE_ANOMALY_RATE`.

Ground truth is stored separately in `backend/data/ground_truth.json`. The metrics endpoint is the only backend API module that reads ground truth for evaluation.

### Reference benchmark

On the bundled reference dataset:

```text
Precision: 1.0
Recall:    1.0
F1:        1.0
Planted anomalies: 1,042
```

The repository also reports measured processing information from the audit execution, including records processed and reconciliation time. Benchmark numbers are derived from execution rather than generated by the UI.

These metrics are for the synthetic reference dataset and should not be interpreted as production fraud/reconciliation performance.

## API surface

The backend exposes the following primary endpoints:

```text
GET  /api/health
GET  /api/readiness

POST /api/audit/run?mode=normal|failure
GET  /api/cases?mode=normal|failure&page=1&page_size=50
GET  /api/cases/{case_id}?mode=normal|failure
POST /api/cases/{case_id}/investigate?mode=normal|failure
POST /api/cases/{case_id}/approve

POST /api/failure-mode/bank-feed
GET  /api/metrics?mode=normal|failure
GET  /api/audit-log
```

`/api/readiness` reports dataset readiness and AI provider state without exposing provider credentials.

## Repository structure

```text
casefile/
├── backend/
│   ├── api/
│   │   ├── routes_approve.py
│   │   ├── routes_audit.py
│   │   ├── routes_cases.py
│   │   ├── routes_investigate.py
│   │   ├── routes_metrics.py
│   │   └── store.py
│   ├── audit/
│   │   └── audit_log.py
│   ├── data/
│   │   ├── generate.py
│   │   ├── generate_dataset.py
│   │   ├── orders.csv
│   │   ├── payments.csv
│   │   ├── refunds.csv
│   │   ├── fees.csv
│   │   ├── settlements.csv
│   │   ├── bank_credits.csv
│   │   ├── ground_truth.json
│   │   └── dataset_meta.json
│   ├── engine/
│   │   ├── loader.py
│   │   ├── chain_walker.py
│   │   ├── rules.py
│   │   ├── evidence.py
│   │   ├── scoring.py
│   │   ├── classification.py
│   │   ├── failure_sim.py
│   │   ├── metrics.py
│   │   └── audit_engine.py
│   ├── llm/
│   │   ├── providers.py
│   │   ├── investigator.py
│   │   ├── prompt.py
│   │   └── client.py
│   ├── models/
│   │   └── schemas.py
│   ├── config.py
│   ├── main.py
│   └── tests/
│       └── run_tests.py
├── src/
│   ├── components/
│   ├── imports/
│   └── lib/
├── docs/
│   ├── architecture.md
│   └── demo_script.md
├── scripts/
│   ├── run_demo.sh
│   └── reset_demo.sh
├── package.json
└── README.md
```

## Running the backend

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Configure the AI provider through environment variables. For example:

```bash
export AI_PROVIDER=gemini
export REQUIRE_AI=true
export GEMINI_API_KEY="<your-key>"
```

Generate the reference dataset if needed:

```bash
python -m backend.data.generate --records 100000 --seed 42
```

Start the API:

```bash
uvicorn backend.main:app --reload --port 8000
```

## Running the frontend

Install dependencies:

```bash
pnpm install
```

Start Vite against the backend:

```bash
VITE_API_BASE=http://localhost:8000 pnpm dev
```

The repository also contains:

```bash
./scripts/run_demo.sh
```

## Offline mode

For development without a live AI provider:

```bash
AI_PROVIDER=deterministic
```

This mode is explicitly deterministic and must not be presented as a real AI investigation.

When the backend is unavailable, the hosted/static frontend can use its deterministic offline preview path. That preview is not authoritative and is not real AI.

For judging or production-style execution, connect the frontend to the FastAPI backend and use a real configured provider.

## Testing

Run the backend test suite from the repository root:

```bash
python backend/tests/run_tests.py
```

The tests cover the deterministic engine, dataset integrity, ground-truth isolation, anomaly detection, classification, scoring, failure simulation, pagination, metrics, and related backend behavior.

## Design decisions

### Deterministic finance, probabilistic reasoning

Financial amounts and classifications that drive operational decisions must be reproducible. The LLM therefore operates after the financial engine rather than inside it.

### Evidence before confidence

Confidence is derived from the availability and consistency of evidence. Removing a required source changes the state of the case.

### Explicit uncertainty

When evidence is insufficient, the system routes the case to human review instead of inventing certainty.

### Bounded automation

The system can investigate and draft recommendations, but approval remains a human-controlled boundary. No autonomous movement of funds is implemented.

### Provider independence

The financial engine does not depend on Gemini, OpenAI, or Claude. Provider selection is an infrastructure concern, not a financial-logic concern.

## Limitations

This repository is a hackathon implementation, not a production financial-control system.

Current limitations include:

- the bundled data is synthetic
- production-scale persistence, authentication, authorization, and secret management are not implemented
- provider availability and model behavior depend on the selected external AI API
- the reference benchmark measures the bundled synthetic dataset, not real merchant traffic
- the approval endpoint records an approval/audit event but does not execute downstream financial operations
- the current failure simulation focuses on bank-feed availability

These boundaries are intentional. CaseFile demonstrates the investigation/control architecture without claiming production deployment readiness.

## Core principle

**The system has a license to investigate. It does not have a license to act.**
