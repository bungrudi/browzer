"""Screenshot capture + vision observation helpers."""

from __future__ import annotations

from browzer.bridge import CodexBridge
from browzer.vision.client import VisionClient

DEFAULT_SYSTEM_PROMPT = (
    "You are a web page observer. Describe only what is visible in the screenshot. "
    "Be concise, factual, and action-oriented. Mention key UI elements, form fields, "
    "buttons, links, dialogs, and visible errors. Do not guess hidden content."
)


async def capture_screenshot(
    bridge: CodexBridge,
    tab_id: int,
    quality: int = 80,
) -> str:
    """Capture a tab screenshot via CDP and return base64 PNG data."""
    result = await bridge.execute_cdp(
        tab_id,
        "Page.captureScreenshot",
        {"format": "png", "quality": quality},
    )
    return str(result.get("data", ""))


async def observe(
    bridge: CodexBridge,
    vision_client: VisionClient,
    tab_id: int,
    instruction: str,
    system_prompt: str | None = None,
) -> dict:
    """Capture screenshot and return vision-model observations."""
    image_base64 = await capture_screenshot(bridge, tab_id)
    observations = await vision_client.describe(
        image_base64=image_base64,
        instruction=instruction,
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
    )
    return {"ok": True, "observations": observations}
