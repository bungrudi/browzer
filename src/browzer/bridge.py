"""Codex Chrome extension bridge — high-level API.

Wraps the low-level CodexTransport with typed, intent-revealing
methods for every bridge operation: tab listing, creation, claiming,
debugger attachment, and raw CDP command execution.

All methods are async and raise BridgeError / TransportError on failure.
"""

from __future__ import annotations

from browzer.transport import BridgeError, CodexTransport

__all__ = ["BridgeError", "CodexBridge"]


class CodexBridge:
    """High-level operations on the Codex Chrome extension bridge.

    Talks to the Codex Native Host Bridge over WebSocket (port 9224)
    using JSON-RPC 2.0. Provides tab listing, creation, claiming,
    debugger attachment, and raw CDP command execution.

    Usage::

        transport = CodexTransport("ws://127.0.0.1:9224", "browzer")
        await transport.connect()
        bridge = CodexBridge(transport)

        tabs = await bridge.get_user_tabs()
        tab = await bridge.create_tab()
        await bridge.claim_user_tab(tab["id"])
        await bridge.attach(tab["id"])
        await bridge.execute_cdp(tab["id"], "Page.navigate", {"url": "https://example.com"})
    """

    def __init__(self, transport: CodexTransport) -> None:
        self._transport = transport

    # ------------------------------------------------------------------
    # Tab listing
    # ------------------------------------------------------------------

    async def get_user_tabs(self) -> list[dict]:
        """List all open user tabs visible to the Codex extension.

        Returns a list of tab objects, each with ``id``, ``title``,
        ``url``, and ``lastOpened`` fields.
        """
        result = await self._transport.rpc("getUserTabs")
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Tab creation
    # ------------------------------------------------------------------

    async def create_tab(self) -> dict:
        """Create a new blank tab.

        Returns a dict with ``id``, ``title`` (empty), ``active``,
        and ``url`` (empty). The tab opens as ``about:blank``.
        Use :meth:`execute_cdp` with ``Page.navigate`` to load a URL.
        """
        return await self._transport.rpc("createTab")

    # ------------------------------------------------------------------
    # Tab ownership & debugger
    # ------------------------------------------------------------------

    async def claim_user_tab(self, tab_id: int) -> None:
        """Claim ownership of a tab for CDP access.

        Must be called before :meth:`attach`. Fails if the tab
        belongs to a different bridge session.
        """
        await self._transport.rpc("claimUserTab", {"tabId": tab_id})

    async def attach(self, tab_id: int) -> None:
        """Attach the Chrome debugger to a tab.

        Required before any :meth:`execute_cdp` calls. The debugger
        stays attached until the WebSocket disconnects.
        """
        await self._transport.rpc("attach", {"tabId": tab_id})

    async def detach(self, tab_id: int) -> None:
        """Detach the debugger from a tab.

        Safe to call even if not attached — errors are suppressed.
        Useful before re-attaching to clean up stale state.
        """
        try:
            await self._transport.rpc("detach", {"tabId": tab_id})
        except BridgeError:
            pass  # May already be detached

    # ------------------------------------------------------------------
    # CDP execution
    # ------------------------------------------------------------------

    async def execute_cdp(
        self,
        tab_id: int,
        method: str,
        command_params: dict | None = None,
    ) -> dict:
        """Execute a raw Chrome DevTools Protocol command on a tab.

        Args:
            tab_id: The target tab ID.
            method: CDP method (e.g., ``"Page.navigate"``,
                    ``"Runtime.evaluate"``, ``"Page.captureScreenshot"``).
            command_params: Parameters for the CDP method.

        Returns:
            The CDP result dict.

        Examples::

            # Navigate
            await bridge.execute_cdp(tab_id, "Page.navigate",
                                     {"url": "https://example.com"})

            # Evaluate JavaScript
            await bridge.execute_cdp(tab_id, "Runtime.evaluate",
                                     {"expression": "document.title",
                                      "returnByValue": True})

            # Screenshot
            await bridge.execute_cdp(tab_id, "Page.captureScreenshot",
                                     {"format": "png"})

            # Accessibility tree
            await bridge.execute_cdp(tab_id, "Accessibility.getFullAXTree")
        """
        return await self._transport.rpc(
            "executeCdp",
            {
                "target": {"tabId": tab_id},
                "method": method,
                "commandParams": command_params or {},
            },
        )

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def get_info(self) -> dict:
        """Get extension metadata from the bridge.

        Returns a dict with ``name``, ``version``, ``type``, and
        ``capabilities`` fields.
        """
        return await self._transport.rpc("getInfo")
