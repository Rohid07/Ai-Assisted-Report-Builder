"""LLM provider abstraction (§5, §6).

Groq and OpenRouter are OpenAI-compatible, so one `openai.OpenAI` client
serves all three providers — only base_url / model / key differ.
Keys are read server-side only, decrypted via the Password fieldtype.
"""

import frappe
from openai import OpenAI

# Keyed by the `active_provider` Select values on AI Assistant Settings.
PROVIDER_CONFIG = {
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_field": "groq_api_key",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "qwen/qwen3-8b:free",
        "key_field": "openrouter_api_key",
    },
    "Gemini": {
        # Google's OpenAI-compatible endpoint (free tier via AI Studio key).
        # Use the "-latest" alias so we track the current flash model instead
        # of a pinned version that gets deprecated (404) with a stale quota.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-flash-latest",
        "key_field": "gemini_api_key",
    },
    "Cerebras": {
        # Generous free tier, fast, OpenAI-compatible, strong tool calling.
        "base_url": "https://api.cerebras.ai/v1",
        "model": "gpt-oss-120b",
        "key_field": "cerebras_api_key",
    },
    "Ollama": {
        "base_url": "http://localhost:11434/v1",
        # Small tool-capable model chosen for low-RAM / CPU-only hosts.
        "model": "qwen2.5:3b",
        "key_field": None,
    },
}


def _make_client(name, settings):
    """Return (client, model, name) for one provider, or None if no usable key."""
    cfg = PROVIDER_CONFIG[name]
    if cfg["key_field"]:
        api_key = settings.get_password(cfg["key_field"], raise_exception=False)
    else:
        api_key = "ollama"  # local server ignores the key
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=cfg["base_url"]), cfg["model"], name


def get_client(provider=None):
    """Return (OpenAI client, model_name) for the active or given provider."""
    settings = frappe.get_single("AI Assistant Settings")
    provider = provider or settings.active_provider or "Groq"
    if provider not in PROVIDER_CONFIG:
        frappe.throw(f"Unknown LLM provider: {provider}")
    made = _make_client(provider, settings)
    if not made:
        frappe.throw(f"No API key configured for {provider}.")
    return made[0], made[1]


def get_provider_chain(provider=None):
    """Ordered [(client, model, name), ...]: active provider first, then any
    other provider with usable credentials — for rate-limit fallback (§Phase 5).

    Ollama is always kept as the FINAL fallback: it is local and unlimited, so
    when every cloud provider is rate-limited/exhausted the assistant still
    answers. (If the local server is down the attempt fails cleanly and the
    request falls through to a graceful message.)"""
    settings = frappe.get_single("AI Assistant Settings")
    active = provider or settings.active_provider or "Groq"
    order = [active] + [p for p in PROVIDER_CONFIG if p != active]

    chain = []
    for name in order:
        made = _make_client(name, settings)
        if made:
            chain.append(made)

    # Keep Ollama last as the unlimited local safety net — unless the user
    # explicitly chose it as the active provider (then it stays first).
    if active != "Ollama":
        chain.sort(key=lambda c: c[2] == "Ollama")
    return chain
