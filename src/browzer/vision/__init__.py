"""Vision mediation layer — screenshot capture and LLM-powered observation."""

from browzer.vision.client import VisionClient
from browzer.vision.observe import observe

__all__ = ["VisionClient", "observe"]
