"""Run an AI investigation over an evidence packet — provider-agnostic.

Selects the configured provider (Gemini / OpenAI / Claude) via the providers
abstraction, parses + validates the JSON via pydantic, retries once, and:
  - on success tags the result with the real provider name (generated_by).
  - on failure, returns an explicit "unavailable" object when REQUIRE_AI is set,
    otherwise a clearly-labelled deterministic fallback (development only).
The backend attaches the Python-computed confidence; the model never sets it.
"""
import json

from .. import config
from ..models.schemas import Investigation
from . import prompt, providers


def _strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
        # drop a possible leading "json"
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def _parse(text, generated_by):
    data = json.loads(_strip_fences(text))
    # The model must never set confidence; drop it defensively.
    data.pop("confidence", None)
    # generated_by is authoritative and set by us, not the model, so it always
    # honestly reflects which provider actually produced the text.
    data["generated_by"] = generated_by
    return Investigation(**data)


def _fallback(case):
    packet = case["evidence_packet"]
    dv = packet["derived_values"]
    complete = packet["evidence_complete"]
    facts = [
        "Flagged anomaly type: %s" % case["type"],
        "Gross payment: %s" % dv["gross_payment"],
        "Expected settlement: %s" % dv["expected_settlement"],
        "Actual settlement: %s" % dv["actual_settlement"],
        "Bank credit: %s" % dv["bank_credit_amount"],
        "Unexplained gap: %s" % dv["unexplained_gap"],
    ]
    if packet["missing_evidence"]:
        facts.append("Missing evidence: %s" % ", ".join(packet["missing_evidence"]))
    return Investigation(
        summary="Automated fallback assessment for %s on payment %s."
        % (case["type"], case["payment_id"]),
        facts=facts,
        root_cause_hypothesis=(
            "HYPOTHESIS: %s is indicated by the reconciliation gap in the "
            "engine-provided facts." % case["type"]
        ),
        alternative_explanations=[
            "HYPOTHESIS: timing difference between settlement and bank feed.",
            "HYPOTHESIS: an unrecorded fee or adjustment.",
        ],
        contradictory_evidence=packet["conflicts"],
        evidence_sufficiency="SUFFICIENT" if complete else "INSUFFICIENT",
        recommended_action=(
            "Escalate to a human reviewer; do not release or adjust funds."
            if not complete
            else "Draft a reconciliation exception for human approval."
        ),
        reasoning=(
            "Generated deterministically without the LLM (unavailable or "
            "invalid response). Reasoning is limited to the engine-provided facts."
        ),
        generated_by="fallback",
    )


def _unavailable(case, provider_name):
    """Explicit 'AI unavailable' object used when REQUIRE_AI is set and the live
    call fails. We never dress deterministic reasoning up as a real provider."""
    who = provider_name or "the selected AI provider"
    return Investigation(
        summary="AI INVESTIGATION UNAVAILABLE — %s could not be reached and "
        "REQUIRE_AI is enabled." % who,
        facts=[],
        root_cause_hypothesis="AI INVESTIGATION UNAVAILABLE",
        alternative_explanations=[],
        contradictory_evidence=case["evidence_packet"]["conflicts"],
        evidence_sufficiency="INSUFFICIENT",
        recommended_action="Retry once the AI provider is reachable, or set "
        "REQUIRE_AI=false to allow deterministic fallback reasoning.",
        reasoning="No AI reasoning was produced. The deterministic financial "
        "facts remain valid and are shown in the evidence packet.",
        generated_by="unavailable",
    )


def investigate(case):
    """Return an Investigation for a case dict. Never raises.

    Routes through the configured provider (config.AI_PROVIDER). On any provider
    failure: explicit 'unavailable' when REQUIRE_AI, else deterministic fallback.
    """
    packet = case["evidence_packet"]
    user_message = prompt.build_user_message(packet, case["type"])

    provider = providers.get_provider()
    if provider is None:
        # No real provider selected (AI_PROVIDER=deterministic / fallback dev path).
        return _fallback(case)

    for _ in range(2):  # initial + one retry
        try:
            text = provider.complete(prompt.SYSTEM_PROMPT, user_message)
            return _parse(text, provider.name)
        except Exception:  # noqa: BLE001 - handled below, never silently masked
            continue

    # A real provider was selected but the live call failed. Honesty over
    # disguise: never auto-switch a configured provider (e.g. Gemini) to the
    # deterministic fallback. Only fall back when explicitly opted-in AND not in
    # REQUIRE_AI mode; otherwise surface an explicit "unavailable" object.
    if not config.REQUIRE_AI and config.ALLOW_AI_FALLBACK:
        return _fallback(case)
    return _unavailable(case, provider.name)
