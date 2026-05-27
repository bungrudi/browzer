"""Execute browser actions (click, fill, scroll) by element ref."""

from dataclasses import dataclass

from browzer.bridge import CodexBridge
from browzer.element_store import ElementStore
from browzer.state_engine import StateEngine


@dataclass
class ActionResult:
    """Result of a browser action."""

    ok: bool
    action: str
    ref: str | None = None
    details: str = ""
    state_delta: dict | None = None


class ActionEngine:
    """Executes browser interactions by stable element refs.

    Resolves refs through the element store, dispatches CDP
    commands for mouse/keyboard/input events, and returns
    state deltas for efficient incremental updates.
    """

    def __init__(
        self,
        bridge: CodexBridge,
        element_store: ElementStore,
        state_engine: StateEngine,
    ) -> None:
        self.bridge = bridge
        self.element_store = element_store
        self.state_engine = state_engine

    async def click_ref(self, tab_id: int, ref: str) -> ActionResult:
        """Click an element by its ref (e.g., '@e3')."""
        ...

    async def fill_ref(
        self, tab_id: int, ref: str, text: str, submit: bool = False
    ) -> ActionResult:
        """Fill an input element by ref. Optionally submit (Enter)."""
        ...

    async def scroll(
        self, tab_id: int, direction: str = "down", pages: float = 1.0
    ) -> ActionResult:
        """Scroll the page by a number of viewport-pages."""
        ...

    async def press_key(self, tab_id: int, key: str) -> ActionResult:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        ...
