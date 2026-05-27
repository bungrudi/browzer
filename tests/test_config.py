"""Tests for Browzer configuration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browzer.config import BrowzerConfig


def test_defaults():
    """Default config values match expected."""
    c = BrowzerConfig()
    assert c.bridge_url == "ws://127.0.0.1:9224"
    assert c.vision_model == "gemini-2.5-flash-lite"
    assert c.drive_mode == "mediated"
    assert c.vision_max_tokens == 1024
    assert c.vision_temperature == 0.0
    assert c.screenshot_quality == 80
    assert c.screenshot_width is None
    assert c.session_timeout == 300


def test_from_env(monkeypatch):
    """from_env reads environment variables."""
    monkeypatch.setenv("BROWZER_VISION_MODEL", "gpt-5.5")
    monkeypatch.setenv("BROWZER_DRIVE_MODE", "vision")
    monkeypatch.setenv("BROWZER_SCREENSHOT_QUALITY", "50")
    monkeypatch.setenv("BROWZER_SCREENSHOT_WIDTH", "1920")

    c = BrowzerConfig.from_env()
    assert c.vision_model == "gpt-5.5"
    assert c.drive_mode == "vision"
    assert c.screenshot_quality == 50
    assert c.screenshot_width == 1920


def test_from_env_defaults():
    """from_env falls back to defaults when vars not set."""
    # Clear any test vars
    for key in list(os.environ):
        if key.startswith("BROWZER_") or key.startswith("CODEX_"):
            del os.environ[key]

    c = BrowzerConfig.from_env()
    assert c.bridge_url == "ws://127.0.0.1:9224"
    assert c.vision_model == "gemini-2.5-flash-lite"
    assert c.drive_mode == "mediated"
    assert c.screenshot_width is None


if __name__ == "__main__":
    test_defaults()
    test_from_env_defaults()
    print("All config tests passed")
