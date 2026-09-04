# CaseFile — 5-minute demo script

| Time | Beat |
|---|---|
| 0:00–0:30 | "Finance teams don't lose money because they can't calculate. They lose it because the evidence is scattered across six systems that don't talk to each other." |
| 0:30–1:00 | Load the **100,000-transaction** interconnected dataset (≈530K linked records) via backend `/api/audit/run`. Call out: this is real backend reconciliation, not a mock. |
| 1:00–1:30 | Overview: canonical transactions, linked records, explained/exceptions/needs-review, ₹ exposure, throughput (records/sec) — all measured by the backend. |
| 1:30–2:30 | Open the **hero case** (settlement under-credit). Payment ₹20,000 − refund ₹1,000 − fees ₹580 = expected ₹18,420, but actual settlement and bank credit are ₹16,420 → **₹2,000 unexplained gap**. The AI returns FACT / HYPOTHESIS / RECOMMENDATION; the ₹2,000 was computed by Python, not Claude. |
| 2:30–3:00 | Show the priority ranking across all cases. |
| 3:00–3:30 | Click **Approve** — it creates a draft and writes to the audit trail. It never moves money. |
| 3:30–4:15 | Toggle **Simulate bank feed offline** and re-run. The hero case flips `EXCEPTION @ 93%` → `NEEDS_HUMAN_REVIEW @ 52%`. The number changed because the *evidence* changed, not the UI. |
| 4:15–4:45 | Metrics: precision / recall / F1 vs. hidden ground truth, computed live. |
| 4:45–5:00 | Close: "It has a license to investigate. It does not have a license to act." One line, then stop. |

**Talking points for Q&A**
- Deterministic math for everything numeric; Claude only narrates and reasons. Say it on camera.
- The 3:30 beat is the strongest card — the confidence drop is real backend behaviour. Don't cut it.
- Razorpay's own Agent Studio is built on Claude's Agent SDK — same foundation they already trust.
