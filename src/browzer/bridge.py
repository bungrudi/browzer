"""Codex Chrome extension bridge — high-level API."""

from browzer.transport import CodexTransport


class BridgeError(Exception):
    """Error returned by the Codex Chrome bridge."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bridge error [{code}]: {message}")


class CodexBridge:
    """High-level operations on the Codex Chrome extension bridge.

    Talks to the Codex Native Host Bridge over WebSocket (port 9224)
    using JSON-RPC 2.0. Provides tab listing, creation, claiming,
    debugger attachment, and raw CDP command execution.
    """

    def __init__(self, transport: CodexTransport) -> None:
        self.transport = transport

    async def get_user_tabs(self) -> list[dict]:
        """List all open user tabs."""
        ...

    async def create_tab(self) -> dict:
        """Create a new blank tab."""
        ...

    async def claim_user_tab(self, tab_id: int) -> None:
        """Claim ownership of a tab for CDP access."""
        ...

    async def attach(self, tab_id: int) -> None:
        """Attach debugger to a tab."""
        ...

    async def detach(self, tab_id: int) -> None:
        """Detach debugger from a tab."""
        ...

    async def execute_cdp(
        self, tab_id: int, method: str, command_params: dict | None = None
    ) -> dict:
        """Execute a raw CDP command on a tab."""
        ...

    async def get_info(self) -> dict:
        """Get extension info from the bridge."""
        ...
