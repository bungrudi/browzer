"""DOM → indexed page state engine.

Converts raw DOM and accessibility tree data into compact,
LLM-friendly page state with indexed interactive elements.
"""

from browzer.bridge import CodexBridge
from browzer.element_store import ElementStore
from browzer.tab_manager import TabManager


class StateEngine:
    """Builds indexed page state from the browser.

    Queries the page via CDP (Runtime.evaluate, Accessibility.getFullAXTree),
    detects interactive elements using browser-use heuristics,
    and produces compact text and JSON representations.
    """

    def __init__(
        self,
        bridge: CodexBridge,
        element_store: ElementStore,
        tab_manager: TabManager,
    ) -> None:
        self.bridge = bridge
        self.element_store = element_store
        self.tab_manager = tab_manager

    async def build_text_state(self, tab_id: int) -> str:
        """Build LLM-friendly text representation of page state."""
        ...

    async def build_json_state(self, tab_id: int) -> dict:
        """Build structured JSON page state."""
        ...
