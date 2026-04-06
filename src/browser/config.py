"""Browser configuration — mirrors AgentRuntimeConfig pattern."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BrowserConfig:
    headless: bool = False
    # persistent session cache directory (gitignored)
    user_data_dir: Path = field(default_factory=lambda: Path(".browser_session"))
    # viewport
    viewport_width: int = 1280
    viewport_height: int = 800
    # timeouts (ms)
    default_timeout: int = 30_000
    navigation_timeout: int = 60_000
    # stealth: randomise user-agent per launch
    randomise_user_agent: bool = True
    # slow-mo (ms) — humanises interactions
    slow_mo: int = 80
    # locale / timezone
    locale: str = "en-US"
    timezone: str = "America/New_York"
    # screenshot quality
    screenshot_type: str = "jpeg"
    screenshot_quality: int = 80

    @classmethod
    def from_dict(cls, d: dict) -> "BrowserConfig":
        valid = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in valid})
