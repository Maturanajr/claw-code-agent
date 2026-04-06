from __future__ import annotations
from pathlib import Path

# Directories to skip in the file tree
IGNORE_DIRS: set[str] = {
    ".git", "__pycache__", ".port_sessions",
    "venv", ".venv", "node_modules", ".mypy_cache",
}

# File extension → emoji icon
FILE_ICONS: dict[str, str] = {
    ".py":   "🐍",
    ".md":   "📝",
    ".json": "📋",
    ".txt":  "📄",
    ".sh":   "⚙️",
    ".env":  "🔑",
    ".toml": "⚙️",
    ".yaml": "⚙️",
    ".yml":  "⚙️",
    ".js":   "🟨",
    ".ts":   "🔷",
    ".tsx":  "🔷",
    ".jsx":  "🟨",
    ".html": "🌐",
    ".css":  "🎨",
    ".png":  "🖼️",
    ".jpg":  "🖼️",
    ".jpeg": "🖼️",
    ".gif":  "🖼️",
    ".svg":  "🖼️",
    ".csv":  "📊",
    ".sql":  "🗄️",
    ".lock": "🔒",
    ".log":  "📜",
}

# Role icons used in chat
ROLE_ICONS: dict[str, str] = {
    "user":      "👤",
    "assistant": "🐾",
    "error":     "⚠️",
    "thinking":  "🤔",
    "writing":   "✍️",
    "tool":      "🔧",
}

# Slash command list
SLASH_COMMANDS: list[str] = [
    "/help", "/context", "/tools", "/memory",
    "/status", "/permissions", "/model", "/clear",
    "/tasks", "/plan", "/browser",
]


def file_icon(name: str) -> str:
    """Return emoji icon for a filename based on its extension."""
    return FILE_ICONS.get(Path(name).suffix.lower(), "📄")
