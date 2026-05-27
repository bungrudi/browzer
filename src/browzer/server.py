"""FastMCP server wiring for Browzer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from browzer.action_engine import ActionEngine
from browzer.bridge import CodexBridge
from browzer.config import BrowzerConfig
from browzer.element_store import ElementStore
from browzer.state_engine import StateEngine
from browzer.tab_manager import TabManager
from browzer.transport import CodexTransport
from browzer.vision.client import VisionClient
from browzer.vision.observe import observe

logger = logging.getLogger(__name__)

# Global runtime singletons used by tool handlers.
_transport: CodexTransport | None = None
_bridge: CodexBridge | None = None
_tab_manager: TabManager | None = None
_element_store: ElementStore | None = None
_state_engine: StateEngine | None = None
_action_engine: ActionEngine | None = None
_vision_client: VisionClient | None = None


def _components_ready() -> bool:
    return all(
        (
            _transport is not None,
            _bridge is not None,
            _tab_manager is not None,
            _element_store is not None,
            _state_engine is not None,
            _action_engine is not None,
        )
    )


async def _ensure_attached(tab_id: int) -> None:
    """Ensure Browzer has an active debugger attachment for a tab.

    The Codex bridge debugger attachment can be lost when another bridge
    client touches the same tab/session or after transport reconnects. Tool
    handlers should call this before every CDP-dependent operation instead of
    assuming the attachment from browser_start is still alive.
    """
    if _tab_manager is None:
        raise RuntimeError("Tab manager not initialized")
    await _tab_manager.claim_and_attach(tab_id)


def create_server(config: BrowzerConfig | None = None) -> FastMCP:
    """Create and configure the Browzer MCP server."""
    cfg = config or BrowzerConfig.from_env()

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        global _transport
        global _bridge
        global _tab_manager
        global _element_store
        global _state_engine
        global _action_engine
        global _vision_client

        logger.info("Starting Browzer server")
        _transport = CodexTransport(cfg.bridge_url, cfg.bridge_session_id)
        await _transport.connect()

        _bridge = CodexBridge(_transport)
        _tab_manager = TabManager(_bridge)
        _element_store = ElementStore()
        _state_engine = StateEngine(_bridge, _element_store, _tab_manager)
        _action_engine = ActionEngine(_bridge, _element_store, _state_engine)

        try:
            _vision_client = VisionClient(cfg)
        except Exception:
            logger.exception("Failed to initialize vision client")
            _vision_client = None

        try:
            yield
        finally:
            logger.info("Shutting down Browzer server")
            if _transport is not None:
                await _transport.disconnect()

            _transport = None
            _bridge = None
            _tab_manager = None
            _element_store = None
            _state_engine = None
            _action_engine = None
            _vision_client = None

    mcp = FastMCP("browzer", lifespan=lifespan)

    @mcp.tool()
    async def browser_start(url: str, mode: str = "text", reuse: bool = True) -> dict:
        """Open or reuse a tab and return tab metadata."""
        del mode
        try:
            if not _components_ready() or _tab_manager is None:
                return {"ok": False, "error": "Server not initialized"}

            tabs_before = await _tab_manager.list_tabs()
            existing_ids = {t.id for t in tabs_before}

            tab = await _tab_manager.get_or_open_tab(url=url, reuse=reuse)
            tabs_after = await _tab_manager.list_tabs()
            latest = next((t for t in tabs_after if t.id == tab.id), tab)

            return {
                "tab_id": latest.id,
                "reused": latest.id in existing_ids,
                "url": latest.url or url,
                "title": latest.title,
            }
        except Exception as exc:
            logger.exception("browser_start failed")
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    async def browser_state(tab_id: int, format: str = "text") -> str | dict:
        """Get current browser state in text or JSON format."""
        try:
            if not _components_ready() or _state_engine is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            if format.lower() == "json":
                return await _state_engine.build_json_state(tab_id)
            return await _state_engine.build_text_state(tab_id)
        except Exception as exc:
            logger.exception("browser_state failed")
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    async def browser_observe(
        tab_id: int, instruction: str, system_prompt: str | None = None
    ) -> dict:
        """Observe visible page content with screenshot + vision model."""
        try:
            if not _components_ready() or _bridge is None:
                return {"ok": False, "error": "Server not initialized"}
            if _vision_client is None:
                return {"ok": False, "error": "Vision client unavailable"}

            await _ensure_attached(tab_id)
            return await observe(_bridge, _vision_client, tab_id, instruction, system_prompt)
        except Exception as exc:
            logger.exception("browser_observe failed")
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    async def browser_click_ref(tab_id: int, ref: str) -> dict:
        """Click an indexed element reference."""
        try:
            if not _components_ready() or _action_engine is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            result = await _action_engine.click_ref(tab_id, ref)
            return {"ok": result.ok, "ref": ref, "details": result.details}
        except Exception as exc:
            logger.exception("browser_click_ref failed")
            return {"ok": False, "ref": ref, "details": str(exc)}

    @mcp.tool()
    async def browser_hover_ref(tab_id: int, ref: str) -> dict:
        """Hover an indexed element reference."""
        try:
            if not _components_ready() or _action_engine is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            result = await _action_engine.hover_ref(tab_id, ref)
            return {"ok": result.ok, "ref": ref, "details": result.details}
        except Exception as exc:
            logger.exception("browser_hover_ref failed")
            return {"ok": False, "ref": ref, "details": str(exc)}

    @mcp.tool()
    async def browser_fill_ref(
        tab_id: int, ref: str, text: str, submit: bool = False
    ) -> dict:
        """Fill an indexed input reference, optionally submitting with Enter."""
        try:
            if not _components_ready() or _action_engine is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            result = await _action_engine.fill_ref(tab_id, ref, text, submit)
            return {
                "ok": result.ok,
                "ref": ref,
                "text": text,
                "submitted": submit,
            }
        except Exception as exc:
            logger.exception("browser_fill_ref failed")
            return {
                "ok": False,
                "ref": ref,
                "text": text,
                "submitted": submit,
                "error": str(exc),
            }

    @mcp.tool()
    async def browser_scroll(
        tab_id: int, direction: str = "down", pages: float = 1.0
    ) -> dict:
        """Scroll the page up/down by viewport pages."""
        try:
            if not _components_ready() or _action_engine is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            result = await _action_engine.scroll(tab_id, direction, pages)
            return {"ok": result.ok, "details": result.details}
        except Exception as exc:
            logger.exception("browser_scroll failed")
            return {"ok": False, "details": str(exc)}

    @mcp.tool()
    async def browser_switch_tab(tab_id: int) -> dict:
        """Switch/attach Browzer control to a tab."""
        try:
            if not _components_ready() or _tab_manager is None:
                return {"ok": False, "error": "Server not initialized"}

            await _tab_manager.claim_and_attach(tab_id)
            return {"ok": True, "tab_id": tab_id}
        except Exception as exc:
            logger.exception("browser_switch_tab failed")
            return {"ok": False, "tab_id": tab_id, "error": str(exc)}

    @mcp.tool()
    async def browser_close_tab(tab_id: int) -> dict:
        """Close a Browzer-owned tab."""
        try:
            if not _components_ready() or _tab_manager is None:
                return {"ok": False, "error": "Server not initialized"}

            closed = await _tab_manager.close_tab(tab_id)
            return {"ok": closed, "closed": closed}
        except Exception as exc:
            logger.exception("browser_close_tab failed")
            return {"ok": False, "closed": False, "error": str(exc)}

    @mcp.tool()
    async def browser_cleanup(
        keep_tab_id: int | None = None, dry_run: bool = True
    ) -> dict:
        """Clean up owned/unused tabs."""
        try:
            if not _components_ready() or _tab_manager is None:
                return {"ok": False, "error": "Server not initialized"}

            return await _tab_manager.cleanup(keep_tab_id=keep_tab_id, dry_run=dry_run)
        except Exception as exc:
            logger.exception("browser_cleanup failed")
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    async def browser_eval(tab_id: int, expression: str) -> dict:
        """Evaluate JavaScript with Runtime.evaluate."""
        try:
            if not _components_ready() or _bridge is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            result: dict[str, Any] = await _bridge.execute_cdp(
                tab_id,
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
            )
            return {"result": result}
        except Exception as exc:
            logger.exception("browser_eval failed")
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    async def browser_press_key(tab_id: int, key: str) -> dict:
        """Press a keyboard key on the current tab."""
        try:
            if not _components_ready() or _action_engine is None:
                return {"ok": False, "error": "Server not initialized"}

            await _ensure_attached(tab_id)
            result = await _action_engine.press_key(tab_id, key)
            return {"ok": result.ok, "details": result.details}
        except Exception as exc:
            logger.exception("browser_press_key failed")
            return {"ok": False, "details": str(exc)}

    return mcp


def main() -> None:
    """CLI entrypoint."""
    config = BrowzerConfig.from_env()
    mcp = create_server(config)
    mcp.run()


if __name__ == "__main__":
    main()
