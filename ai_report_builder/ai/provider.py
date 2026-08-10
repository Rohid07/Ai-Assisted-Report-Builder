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
    "Ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3:8b",
        "key_field": None,
    },
}


def get_client(provider=None):
    """Return (OpenAI client, model_name) for the active or given provider."""
    settings = frappe.get_single("AI Assistant Settings")
    provider = provider or settings.active_provider or "Groq"
    if provider not in PROVIDER_CONFIG:
        frappe.throw(f"Unknown LLM provider: {provider}")
    cfg = PROVIDER_CONFIG[provider]

    if cfg["key_field"]:
        api_key = settings.get_password(cfg["key_field"], raise_exception=False)
    else:
        api_key = "ollama"  # local server ignores the key

    if not api_key:
        frappe.throw(f"No API key configured for {provider}.")

    return OpenAI(api_key=api_key, base_url=cfg["base_url"]), cfg["model"]
