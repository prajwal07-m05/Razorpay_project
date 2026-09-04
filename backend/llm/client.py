"""Thin Anthropic client wrapper.

Reads ANTHROPIC_API_KEY and CLAUDE_MODEL from the environment. Kept tiny so
the rest of the app never touches the SDK directly.
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional at runtime
    pass

from ..config import DEFAULT_CLAUDE_MODEL


def get_model():
    return os.environ.get("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)


def is_configured():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(system_prompt, user_message, max_tokens=1500):
    """Call Claude and return the raw text of the first content block.

    Raises if the SDK is unavailable or the key is missing; callers handle
    the fallback path.
    """
    if not is_configured():
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    from anthropic import Anthropic  # imported lazily

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=get_model(),
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    parts = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
