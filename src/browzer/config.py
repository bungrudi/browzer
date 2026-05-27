"""Configuration from environment variables."""

import os
from dataclasses import dataclass


def _int_env(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def _float_env(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _optional_int_env(name: str) -> int | None:
    val = os.getenv(name)
    return int(val) if val else None


@dataclass
class BrowzerConfig:
    """Browzer configuration loaded from environment variables."""

    # Transport — Codex Chrome extension bridge
    bridge_url: str = "ws://127.0.0.1:9224"
    bridge_session_id: str = "browzer"

    # Vision LLM — OpenAI-compatible endpoint (default: gemini-2.5-flash-lite)
    vision_base_url: str = "http://127.0.0.1:2455/v1"
    vision_model: str = "gemini-2.5-flash-lite"
    vision_api_key: str = ""
    vision_max_tokens: int = 1024
    vision_temperature: float = 0.0
    vision_timeout: int = 30

    # Drive mode — "mediated" (vision-enriched text) or "vision" (vision-first)
    drive_mode: str = "mediated"

    # Screenshot settings
    screenshot_quality: int = 80
    screenshot_width: int | None = None  # None = use viewport width

    # Session
    session_timeout: int = 300

    @classmethod
    def from_env(cls) -> "BrowzerConfig":
        """Create a BrowzerConfig from environment variables."""
        return cls(
            bridge_url=os.getenv("CODEX_CHROME_BRIDGE_URL", "ws://127.0.0.1:9224"),
            bridge_session_id=os.getenv("BROWZER_SESSION_ID", "browzer"),
            vision_base_url=os.getenv(
                "BROWZER_VISION_BASE_URL", "http://127.0.0.1:2455/v1"
            ),
            vision_model=os.getenv("BROWZER_VISION_MODEL", "gemini-2.5-flash-lite"),
            vision_api_key=os.getenv("BROWZER_VISION_API_KEY", ""),
            vision_max_tokens=_int_env("BROWZER_VISION_MAX_TOKENS", "1024"),
            vision_temperature=_float_env("BROWZER_VISION_TEMPERATURE", "0"),
            vision_timeout=_int_env("BROWZER_VISION_TIMEOUT", "30"),
            drive_mode=os.getenv("BROWZER_DRIVE_MODE", "mediated"),
            screenshot_quality=_int_env("BROWZER_SCREENSHOT_QUALITY", "80"),
            screenshot_width=_optional_int_env("BROWZER_SCREENSHOT_WIDTH"),
            session_timeout=_int_env("BROWZER_SESSION_TIMEOUT", "300"),
        )
