"""FastMCP server — tool registration and entry point."""

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from browzer.action_engine import ActionEngine
from browzer.bridge import CodexBridge
from browzer.config import BrowzerConfig
from browzer.element_store import ElementStore
from browzer.state_engine import StateEngine
from browzer.tab_manager import TabManager
from browzer.transport import CodexTransport

logger = logging.getLogger(__name__)


def create_server(config: BrowzerConfig | None = None) -> FastMCP:
    """Create and configure the Browzer MCP server."""
    mcp = FastMCP("browzer")

    if config is None:
        config = BrowzerConfig.from_env()

    # Session state — initialized in lifespan
    transport: CodexTransport | None = None
    bridge: CodexBridge | None = None
    tab_manager: TabManager | None = None
    element_store: ElementStore | None = None
    state_engine: StateEngine | None = None
    action_engine: ActionEngine | None = None

    @mcp.tool()
    async def browser_start(
        url: str, mode: str = "text", reuse: bool = True
    ) -> dict:
        """Open or reuse a tab. Returns tab_id and initial info."""
        ...

    @mcp.tool()
    async def browser_state(tab_id: int, format: str = "text") -> str | dict:
        """Get indexed interactive elements + page text for a tab."""
        ...

    @mcp.tool()
    async def browser_observe(
        tab_id: int, instruction: str, system_prompt: str | None = None
    ) -> dict:
        """Send screenshot + instruction to vision LLM for page observation."""
        ...

    @mcp.tool()
    async def browser_click_ref(tab_id: int, ref: str) -> dict:
        """Click an element by its ref (e.g., '@e3')."""
        ...

    @mcp.tool()
    async def browser_fill_ref(
        tab_id: int, ref: str, text: str, submit: bool = False
    ) -> dict:
        """Fill an input by ref. Optionally press Enter after."""
        ...

    @mcp.tool()
    async def browser_scroll(
        tab_id: int, direction: str = "down", pages: float = 1.0
    ) -> dict:
        """Scroll the page up or down."""
        ...

    @mcp.tool()
    async def browser_switch_tab(tab_id: int) -> dict:
        """Switch to a different tab."""
        ...

    @mcp.tool()
    async def browser_close_tab(tab_id: int) -> dict:
        """Close a tab (only Browzer-owned tabs)."""
        ...

    @mcp.tool()
    async def browser_cleanup(
        keep_tab_id: int | None = None, dry_run: bool = True
    ) -> dict:
        """Clean up unused Browzer-controlled tabs. Defaults to dry-run."""
        ...

    @mcp.tool()
    async def browser_eval(tab_id: int, expression: str) -> dict:
        """Evaluate JavaScript in a tab. Returns JSON-serializable result."""
        ...

    return mcp


def main() -> None:
    """Entry point — run the Browzer MCP server."""
    config = BrowzerConfig.from_env()
    server = create_server(config)
    server.run()


if __name__ == "__main__":
    main()
