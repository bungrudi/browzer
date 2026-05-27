"""OpenAI-compatible vision LLM client."""

from browzer.config import BrowzerConfig


class VisionClient:
    """Client for an OpenAI-compatible vision API endpoint.

    Sends screenshots + instructions to a configurable vision
    model and returns text descriptions of page content.
    """

    def __init__(self, config: BrowzerConfig) -> None:
        self.config = config
        self._client = None  # Lazy init

    async def describe(
        self,
        image_base64: str,
        instruction: str,
        system_prompt: str | None = None,
    ) -> str:
        """Send image + instruction to the vision LLM.

        Returns the model's text response describing what it sees.
        """
        ...
