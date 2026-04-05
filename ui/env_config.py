from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import streamlit as st

ENV_PATH = Path(".env")

# OpenRouter public pricing endpoint — no auth required
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def load_env() -> None:
    """Load .env into os.environ, stripping CRLF and quotes."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip().replace("\r", "")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def save_env(base_url: str, api_key: str, model: str) -> None:
    """Persist config to .env and update os.environ."""
    ENV_PATH.write_text(
        f"OPENAI_BASE_URL={base_url}\n"
        f"OPENAI_API_KEY={api_key}\n"
        f"OPENAI_MODEL={model}\n",
        encoding="utf-8",
    )
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_MODEL"] = model


@st.cache_data(ttl=120, show_spinner=False)
def fetch_models(base_url: str, api_key: str) -> list[str]:
    """Call GET /v1/models and return sorted model id list."""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        models = [m["id"] for m in data.get("data", []) if isinstance(m.get("id"), str)]
        return sorted(models)
    except Exception as exc:
        return [f"__error__:{exc}"]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_openrouter_pricing() -> dict[str, dict]:
    """
    Fetch pricing for all models from OpenRouter public API (no auth needed).
    Returns dict: model_id -> {input_per_million, output_per_million}
    pricing.prompt and pricing.completion are per-token strings.
    """
    try:
        req = urllib.request.Request(
            _OPENROUTER_MODELS_URL,
            headers={"User-Agent": "claw-code-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = {}
        for m in data.get("data", []):
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            try:
                prompt_per_token     = float(pricing.get("prompt", 0) or 0)
                completion_per_token = float(pricing.get("completion", 0) or 0)
                result[mid] = {
                    "input_per_million":  prompt_per_token * 1_000_000,
                    "output_per_million": completion_per_token * 1_000_000,
                }
            except (ValueError, TypeError):
                pass
        return result
    except Exception:
        return {}


def get_model_pricing(model: str) -> tuple[float, float]:
    """
    Return (input_cost_per_million, output_cost_per_million) for a model.
    Tries OpenRouter pricing first, then falls back to known OpenAI prices,
    then 0.0 / 0.0.
    """
    # try OpenRouter (covers openai/*, anthropic/*, google/*, etc.)
    pricing = fetch_openrouter_pricing()
    if model in pricing:
        p = pricing[model]
        return p["input_per_million"], p["output_per_million"]

    # OpenRouter also indexes bare OpenAI model names under openai/<name>
    or_key = f"openai/{model}"
    if or_key in pricing:
        p = pricing[or_key]
        return p["input_per_million"], p["output_per_million"]

    # hardcoded fallback for common OpenAI models (USD per million tokens, Apr 2026)
    _OPENAI_FALLBACK: dict[str, tuple[float, float]] = {
        "gpt-4o":              (2.50,  10.00),
        "gpt-4o-mini":         (0.15,   0.60),
        "gpt-4-turbo":         (10.00, 30.00),
        "gpt-4":               (30.00, 60.00),
        "gpt-3.5-turbo":       (0.50,   1.50),
        "o1":                  (15.00, 60.00),
        "o1-mini":             (1.10,   4.40),
        "o3-mini":             (1.10,   4.40),
    }
    for key, val in _OPENAI_FALLBACK.items():
        if model.endswith(key) or model == key:
            return val

    return 0.0, 0.0
