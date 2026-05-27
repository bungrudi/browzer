"""OpenAI-compatible vision LLM client."""

from __future__ import annotations

from openai import AsyncOpenAI

from browzer.config import BrowzerConfig


class VisionClient:
    """Client for an OpenAI-compatible vision API endpoint.

    Sends screenshots + instructions to a configurable vision
    model and returns text descriptions of page content.
    """

    def __init__(self, config: BrowzerConfig) -> None:
        self.config = config
        self._client = AsyncOpenAI(
            base_url=config.vision_base_url,
            api_key=config.vision_api_key,
            timeout=config.vision_timeout,
        )

    async def describe(
        self,
        image_base64: str,
        instruction: str,
        system_prompt: str | None = None,
    ) -> str:
        """Send image + instruction to the vision LLM.

        Returns the model's text response describing what it sees.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            }
        )

        response = await self._client.chat.completions.create(
            model=self.config.vision_model,
            messages=messages,
            max_tokens=self.config.vision_max_tokens,
            temperature=self.config.vision_temperature,
        )
        return (response.choices[0].message.content or "").strip()
