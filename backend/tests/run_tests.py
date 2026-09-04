"""Stdlib-only test runner for the CaseFile engine core.

No pytest, no pandas. Builds datasets IN MEMORY via the deterministic generator
(so tests don't depend on the on-disk 100K CSVs) and exercises the pure-Python
engine. Run:  python3 backend/tests/run_tests.py
"""
import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend import config  # noqa: E402
from backend.data import generate  # noqa: E402
from backend.engine import audit_engine, chain_walker, metrics  # noqa: E402
from backend.llm import investigator, providers, prompt  # noqa: E402

_VALID_AI_JSON = json.dumps({
    "summary": "s", "facts": ["f"], "root_cause_hypothesis": "h",
    "alternative_explanations": [], "contradictory_evidence": [],
    "evidence_sufficiency": "SUFFICIENT", "recommended_action": "r",
    "reasoning": "why",
})


class _FakeProvider(providers.AIProvider):
    """Mock provider — never makes a real API call (§16)."""
    def __init__(self, name, text=None, raises=False):
        self.name = name
        self._text = text
        self._raises = raises
    def is_configured(self):
        return True
    def complete(self, system_prompt, user_message, max_tokens=1500):
        if self._raises:
            raise RuntimeError("provider unavailable (mock)")
        return self._text

# A modest, fast dataset with a meaningful number of injected anomalies.
TEST_RECORDS = 1500
TEST_SEED = 42
TEST_RATE = 0.02

_PASS = 0
_FAIL = 0


def check(cond, msg):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  ok   - %s" % msg)
    else:
        _FAIL += 1
        print("  FAIL - %s" % msg)


def cases_for_payment(cases, payment_id):
    return [c for c in cases if c["payment_id"] == payment_id]


def gt_payment(ground_truth, type_):
    return [g["payment_id"] for g in ground_truth if g["type"] == type_]


def run():
    b = generate.build(records=TEST_RECORDS, seed=TEST_SEED, anomaly_rate=TEST_RATE)
    tables = b.tables()
    ground_truth = b.ground_truth

    normal = audit_engine.run_audit(tables, mode="normal")
    failure = audit_engine.run_audit(tables, mode="failure")
    n_cases = normal["cases"]

    print("\n[dataset scale]")
    check(len(tables["orders"]) == TEST_RECORDS,
          "canonical transactions == %d (%d)" % (TEST_RECORDS, len(tables["orders"])))
    total = b.total_records()
    check(total > len(tables["orders"]),
          "total relational records > canonical (%d > %d)" % (total, len(tables["orders"])))
    check(len(ground_truth) >= 15, "planted anomalies >= 15 (%d)" % len(ground_truth))

    print("\n[determinism]")
    b2 = generate.build(records=TEST_RECORDS, seed=TEST_SEED, anomaly_rate=TEST_RATE)
    check(b2.tables() == tables, "same seed => identical tables")
    check(b2.ground_truth == ground_truth, "same seed => identical ground truth")
    b3 = generate.build(records=TEST_RECORDS, seed=TEST_SEED + 1, anomaly_rate=TEST_RATE)
    check(b3.ground_truth != ground_truth, "different seed => different ground truth")

    print("\n[relational integrity]")
    order_ids = {o["order_id"] for o in tables["orders"]}
    payment_ids = {p["payment_id"] for p in tables["payments"]}
    settlement_ids = {s["settlement_id"] for s in tables["settlements"]}
    check(all(p["order_id"] in order_ids for p in tables["payments"]),
          "every payment references a valid order")
    check(all(r["payment_id"] in payment_ids for r in tables["refunds"]),
          "every refund references a valid payment")
    check(all(f["payment_id"] in payment_ids for f in tables["fees"]),
          "every fee references a valid payment")
    check(all(s["payment_id"] in payment_ids for s in tables["settlements"]),
          "every settlement references a valid payment")
    check(all(c["settlement_id"] in settlement_ids for c in tables["bank_credits"]),
          "every bank credit references a valid settlement")

    print("\n[anomaly injection actually modifies records]")
    # Under-credit anomalies must have actual != expected in the settlements.
    uc_pids = set(gt_payment(ground_truth, config.SETTLEMENT_UNDER_CREDIT))
    modified = [s for s in tables["settlements"]
                if s["payment_id"] in uc_pids and s["expected_amt"] != s["actual_amt"]]
    check(len(modified) == len(uc_pids),
          "all under-credit settlements have expected != actual (%d)" % len(modified))

    print("\n[ground truth isolation]")
    # The engine runs with NO access to ground truth and never returns it.
    check("ground_truth" not in normal and "ground_truth" not in normal["summary"],
          "engine result never exposes ground truth")
    src = open(os.path.join(_REPO_ROOT, "backend", "engine", "audit_engine.py")).read()
    check("ground_truth" not in src, "audit_engine.py does not reference ground truth")

    print("\n[anomaly types detected]")
    detected_types = set(c["type"] for c in n_cases)
    for t in [config.SETTLEMENT_UNDER_CREDIT, config.MISSING_SETTLEMENT,
              config.MISSING_BANK_CREDIT, config.DUPLICATE_PAYMENT,
              config.REFUND_EXCEEDS_PAYMENT, config.STATUS_MISMATCH,
              config.DUPLICATE_REFUND]:
        check(t in detected_types, "detected %s" % t)

    print("\n[explained transactions are NOT flagged]")
    flagged_pids = set(c["payment_id"] for c in n_cases)
    truth_pids = set(g["payment_id"] for g in ground_truth)
    leaked = flagged_pids - truth_pids
    check(not leaked, "no non-anomalous payment raised a case (leaked=%d)" % len(leaked))
    check(normal["summary"]["explained"] > TEST_RECORDS * 0.9,
          "vast majority explained (%d)" % normal["summary"]["explained"])

    print("\n[HERO case - normal mode]")
    hero = cases_for_payment(n_cases, "PAY000001")
    check(len(hero) == 1, "hero has exactly one case (%d)" % len(hero))
    hero = hero[0]
    dv = hero["evidence_packet"]["derived_values"]
    check(dv["gross_payment"] == 20000, "hero gross == 20000 (%s)" % dv["gross_payment"])
    check(dv["refund_total"] == 1000, "hero refund == 1000 (%s)" % dv["refund_total"])
    check(dv["fee_total"] == 580, "hero fee == 580 (%s)" % dv["fee_total"])
    check(dv["expected_settlement"] == 18420, "hero expected == 18420 (%s)" % dv["expected_settlement"])
    check(dv["actual_settlement"] == 16420, "hero actual == 16420 (%s)" % dv["actual_settlement"])
    check(dv["unexplained_gap"] == 2000, "hero gap == 2000 (%s)" % dv["unexplained_gap"])
    check(hero["type"] == config.SETTLEMENT_UNDER_CREDIT, "hero type SETTLEMENT_UNDER_CREDIT")
    check(hero["classification"] == config.EXCEPTION,
          "hero classification EXCEPTION (%s)" % hero["classification"])
    check(93 <= hero["confidence"] <= 95, "hero confidence 93..95 (%s)" % hero["confidence"])
    check(hero["amount_at_risk"] == 2000, "hero at_risk == 2000 (%s)" % hero["amount_at_risk"])

    print("\n[HERO case - failure mode]")
    hf = [c for c in cases_for_payment(failure["cases"], "PAY000001")
          if c["type"] == config.SETTLEMENT_UNDER_CREDIT]
    check(len(hf) == 1, "hero still surfaced in failure mode")
    hf = hf[0]
    dvf = hf["evidence_packet"]["derived_values"]
    check(dvf["expected_settlement"] == 18420 and dvf["actual_settlement"] == 16420,
          "hero failure values unchanged (backend recomputed, not UI)")
    check(hf["evidence_packet"]["evidence_complete"] is False, "hero failure evidence incomplete")
    check(hf["classification"] == config.NEEDS_HUMAN_REVIEW,
          "hero failure NEEDS_HUMAN_REVIEW (%s)" % hf["classification"])
    check(52 <= hf["confidence"] <= 55, "hero failure confidence 52..55 (%s)" % hf["confidence"])

    print("\n[failure mode changes evidence + confidence, honestly]")
    check(failure["summary"]["bank_feed_available"] is False, "failure flags feed offline")
    fr_needs = [c for c in failure["cases"] if c["classification"] == config.NEEDS_HUMAN_REVIEW]
    check(fr_needs and all(c["type"] == config.SETTLEMENT_UNDER_CREDIT for c in fr_needs),
          "needs-review cases are all under-credit (%d)" % len(fr_needs))
    check(not any(c["type"] == config.MISSING_BANK_CREDIT for c in failure["cases"]),
          "MISSING_BANK_CREDIT not raised when feed offline (unobservable)")
    for t in [config.MISSING_SETTLEMENT, config.DUPLICATE_PAYMENT,
              config.REFUND_EXCEEDS_PAYMENT, config.STATUS_MISMATCH]:
        nc = len([c for c in n_cases if c["type"] == t])
        fc = len([c for c in failure["cases"] if c["type"] == t])
        check(nc == fc, "%s unaffected by feed outage (n=%d f=%d)" % (t, nc, fc))

    print("\n[status mismatch -> CONFLICTING_EVIDENCE]")
    sm = [c for c in n_cases if c["type"] == config.STATUS_MISMATCH]
    check(sm and all(c["classification"] == config.CONFLICTING_EVIDENCE for c in sm),
          "status mismatch cases are CONFLICTING_EVIDENCE")

    print("\n[pagination contract]")
    ranked = n_cases  # already priority-desc
    page1 = ranked[0:10]
    page2 = ranked[10:20]
    check(len(page1) == 10 and page1[0]["priority_score"] >= page1[-1]["priority_score"],
          "page 1 is priority-ranked")
    check(not (set(c["case_id"] for c in page1) & set(c["case_id"] for c in page2)),
          "pages do not overlap")

    print("\n[metrics vs ground truth - normal mode]")
    m = metrics.compute_metrics(normal, ground_truth,
                                records_processed=len(tables["payments"]))
    print("  metrics: %s" % json.dumps({k: m[k] for k in
          ["precision", "recall", "f1", "true_positives", "false_positives",
           "false_negatives", "true_negatives", "anomalies_planted", "anomalies_detected"]}))
    check(m["precision"] == 1.0, "precision == 1.0 (%s)" % m["precision"])
    check(m["recall"] == 1.0, "recall == 1.0 (%s)" % m["recall"])
    check(m["f1"] == 1.0, "f1 == 1.0 (%s)" % m["f1"])
    check(m["false_positives"] == 0, "false_positives == 0 (%s)" % m["false_positives"])
    check(m["false_negatives"] == 0, "false_negatives == 0 (%s)" % m["false_negatives"])
    check(m["true_negatives"] > 0, "true_negatives > 0 (%s)" % m["true_negatives"])

    print("\n[input tables are not mutated by the engine]")
    before = copy.deepcopy(tables)
    audit_engine.run_audit(tables, mode="failure")
    check(tables == before, "run_audit(failure) does not mutate caller tables")

    print("\n[AI provider abstraction]")
    # Provider selection is config-only; the engine never depends on a vendor.
    check(providers.get_provider("gemini").name == "gemini", "gemini provider selectable")
    check(providers.get_provider("openai").name == "openai", "openai provider selectable")
    check(providers.get_provider("claude").name == "claude", "claude provider optional/selectable")
    check(providers.get_provider("deterministic") is None, "deterministic => no provider (fallback path)")

    _orig_get = providers.get_provider
    hero_case = cases_for_payment(n_cases, "PAY000001")[0]
    try:
        # generated_by is truthful: each provider tags its own name on success.
        for pname in ("gemini", "openai", "claude"):
            providers.get_provider = lambda name=None, _p=pname: _FakeProvider(_p, text=_VALID_AI_JSON)
            inv = investigator.investigate(hero_case)
            check(inv.generated_by == pname, "generated_by == %s when %s produced it" % (pname, pname))

        # REQUIRE_AI=true blocks silent fallback when the provider fails.
        providers.get_provider = lambda name=None: _FakeProvider("gemini", raises=True)
        _saved = config.REQUIRE_AI
        config.REQUIRE_AI = True
        inv = investigator.investigate(hero_case)
        check(inv.generated_by == "unavailable", "REQUIRE_AI=true -> unavailable, not fabricated")
        check("UNAVAILABLE" in inv.summary.upper(), "unavailable summary is explicit")

        # Malformed model output is rejected (not fabricated) -> unavailable.
        providers.get_provider = lambda name=None: _FakeProvider("gemini", text="not json {{{")
        inv = investigator.investigate(hero_case)
        check(inv.generated_by == "unavailable", "malformed AI output rejected under REQUIRE_AI")

        # No silent fallback: a configured provider that fails is NOT auto-swapped
        # for the deterministic fallback unless ALLOW_AI_FALLBACK is explicitly set.
        config.REQUIRE_AI = False
        _saved_fb = config.ALLOW_AI_FALLBACK
        config.ALLOW_AI_FALLBACK = False
        providers.get_provider = lambda name=None: _FakeProvider("gemini", raises=True)
        inv = investigator.investigate(hero_case)
        check(inv.generated_by == "unavailable",
              "provider failure without ALLOW_AI_FALLBACK -> unavailable (no silent fallback)")

        # Fallback is reachable only when explicitly opted-in, labelled honestly.
        config.ALLOW_AI_FALLBACK = True
        providers.get_provider = lambda name=None: _FakeProvider("gemini", raises=True)
        inv = investigator.investigate(hero_case)
        check(inv.generated_by == "fallback",
              "ALLOW_AI_FALLBACK=true -> deterministic fallback (labelled)")

        # Explicitly selecting the deterministic path yields fallback directly.
        config.ALLOW_AI_FALLBACK = False
        providers.get_provider = _orig_get
        _saved_prov = config.AI_PROVIDER
        config.AI_PROVIDER = "deterministic"
        inv = investigator.investigate(hero_case)
        check(inv.generated_by == "fallback", "AI_PROVIDER=deterministic -> deterministic fallback")
        check(providers.get_provider() is None, "AI_PROVIDER=deterministic => no real provider")
        config.AI_PROVIDER = _saved_prov
        config.ALLOW_AI_FALLBACK = _saved_fb
        config.REQUIRE_AI = _saved
    finally:
        providers.get_provider = _orig_get

    # The AI only ever sees the compact evidence packet — never ground truth.
    msg = prompt.build_user_message(hero_case["evidence_packet"], hero_case["type"])
    for leak in ("expected_status", "expected_anomaly", "expected_root_cause", "ground_truth"):
        check(leak not in msg, "AI evidence packet excludes '%s'" % leak)

    print("\n[summary]")
    print("  passed: %d   failed: %d" % (_PASS, _FAIL))
    print("  normal summary: %s" % json.dumps(normal["summary"]))
    return _FAIL == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
