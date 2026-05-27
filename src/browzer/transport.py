"""Low-level WebSocket JSON-RPC client for the Codex bridge."""

import asyncio
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection


class TransportError(Exception):
    """WebSocket or protocol-level transport error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CodexTransport:
    """WebSocket JSON-RPC 2.0 client for the Codex Chrome bridge.

    Manages a persistent WebSocket connection to the bridge on port 9224.
    Handles request/response correlation, auto-injects session_id/turn_id,
    and provides reconnection with exponential backoff.
    """

    def __init__(self, url: str, session_id: str) -> None:
        self.url = url
        self.session_id = session_id
        self._ws: ClientConnection | None = None
        self._lock = asyncio.Lock()
        self._request_id = 0
        self._turn_id = 0

    async def connect(self) -> None:
        """Connect to the bridge WebSocket."""
        ...

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        ...

    async def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict:
        """Send a JSON-RPC request and wait for the response.

        Auto-injects session_id and turn_id into params.
        Thread-safe via asyncio.Lock.
        """
        ...

    @property
    def connected(self) -> bool:
        """Whether the WebSocket is currently connected."""
        return self._ws is not None
