from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st


def init_state() -> None:
    defaults: dict = {
        "messages": [],
        "agent_session_id": None,
        "status": "idle",          # idle | thinking
        "status_text": "",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": 0.0,
        "allow_write": False,
        "allow_shell": False,
        "unsafe": False,
        "model":    os.environ.get("OPENAI_MODEL",    "gpt-4o-mini"),
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key":  os.environ.get("OPENAI_API_KEY",  ""),
        "max_turns": 12,
        "cwd": str(Path(".").resolve()),
        "logs": [],
        "tree_browse_path": str(Path(".").resolve()),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def log(level: str, text: str) -> None:
    st.session_state.logs.append({
        "level": level,
        "text": text,
        "ts": time.strftime("%H:%M:%S"),
    })


def reset_session() -> None:
    st.session_state.agent_session_id = None
    st.session_state.messages = []
    st.session_state.total_input_tokens = 0
    st.session_state.total_output_tokens = 0
    st.session_state.total_cost = 0.0
