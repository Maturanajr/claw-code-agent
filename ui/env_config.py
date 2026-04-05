from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import streamlit as st

ENV_PATH = Path(".env")


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
