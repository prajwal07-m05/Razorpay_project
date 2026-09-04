"""Provider-agnostic AI abstraction for the investigation layer.

Every provider exposes the same tiny contract:

    is_configured() -> bool      # key present in the environment
    complete(system, user) -> str  # raw model text (JSON, per the prompt)

The application selects a provider by name (config.AI_PROVIDER) and never
touches a vendor SDK directly. SDK imports are lazy and per-provider, so the
app runs with only the selected provider's SDK installed — e.g. Gemini works
without `anthropic` present, and vice versa.

API keys are read ONLY from environment variables, never returned by an API,
never sent to the frontend, and never logged.
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional at runtime
    pass

from .. import config


class AIProvider:
    """Base class. `name` is the honest generated_by tag for this provider."""

    name = "base"

    def is_configured(self):  # pragma: no cover - interface
        raise NotImplementedError

    def complete(self, system_prompt, user_message, max_tokens=1500):  # pragma: no cover
        raise NotImplementedError


class ClaudeProvider(AIProvider):
    name = "claude"

    def is_configured(self):
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system_prompt, user_message, max_tokens=1500):
        # Delegate to the existing thin Anthropic wrapper (kept for continuity).
        from . import client

        return client.complete(system_prompt, user_message, max_tokens=max_tokens)


class GeminiProvider(AIProvider):
    name = "gemini"

    def model(self):
        return os.environ.get("GEMINI_MODEL", config.DEFAULT_GEMINI_MODEL)

    def is_configured(self):
        return bool(os.environ.get("GEMINI_API_KEY"))

    def complete(self, system_prompt, user_message, max_tokens=1500):
        if not self.is_configured():
            raise RuntimeError("GEMINI_API_KEY not configured")
        from google import genai  # official google-genai SDK, imported lazily
        from google.genai import types

        gclient = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        resp = gclient.models.generate_content(
            model=self.model(),
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            ),
        )
        text = getattr(resp, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return text


class OpenAIProvider(AIProvider):
    name = "openai"

    def model(self):
        return os.environ.get("OPENAI_MODEL", config.DEFAULT_OPENAI_MODEL)

    def is_configured(self):
        return bool(os.environ.get("OPENAI_API_KEY"))

    def complete(self, system_prompt, user_message, max_tokens=1500):
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY not configured")
        from openai import OpenAI  # official OpenAI SDK, imported lazily

        oclient = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = oclient.chat.completions.create(
            model=self.model(),
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return resp.choices[0].message.content


_PROVIDERS = {
    "claude": ClaudeProvider,
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}


# Names that mean "no real provider — use the deterministic dev/test path".
_DETERMINISTIC = {"", "fallback", "deterministic", "none", "off"}


def selected_name():
    """The configured provider name, normalised. Deterministic aliases collapse
    to 'deterministic' so the frontend/health can label the offline path clearly."""
    name = (config.AI_PROVIDER or "").strip().lower()
    return "deterministic" if name in _DETERMINISTIC else name


def get_provider(name=None):
    """Return the selected AIProvider instance, or None for the deterministic
    (development/testing) path."""
    resolved = (name or selected_name())
    if resolved in _DETERMINISTIC or resolved == "deterministic":
        return None
    cls = _PROVIDERS.get(resolved)
    return cls() if cls else None


def is_ai_configured():
    """True when a real provider is selected AND its key is present."""
    p = get_provider()
    return bool(p and p.is_configured())


def is_ai_reachable():
    """Best-effort reachability: a real provider is selected and its key is
    present. We do NOT make a network call here (that would spend tokens on
    every health poll); a configured key is confirmed by an actual investigation."""
    return is_ai_configured()


def fallback_allowed():
    """Deterministic fallback is only permitted when explicitly opted into —
    either by selecting it as the provider (AI_PROVIDER=deterministic|fallback)
    or via ALLOW_AI_FALLBACK=true. A real provider is NEVER auto-switched to the
    fallback on failure."""
    return selected_name() == "deterministic" or config.ALLOW_AI_FALLBACK
