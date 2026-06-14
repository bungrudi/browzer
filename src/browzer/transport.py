"""Low-level WebSocket JSON-RPC client for the Codex bridge.

Manages a persistent WebSocket connection to the Codex Chrome
extension bridge on port 9224. Handles request/response correlation,
auto-injects session_id/turn_id, and provides reconnection with
exponential backoff.

Protocol: JSON-RPC 2.0 over WebSocket.
Each request gets an auto-incremented id. Responses are matched by id.
session_id and turn_id are injected into every request's params.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

# Reconnection backoff
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0
BACKOFF_MULTIPLIER = 2.0


class TransportError(Exception):
    """WebSocket or protocol-level transport error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BridgeError(Exception):
    """Error returned by the Codex Chrome bridge in a JSON-RPC response."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bridge error [{code}]: {message}")


class CodexTransport:
    """WebSocket JSON-RPC 2.0 client for the Codex Chrome bridge.

    Usage::

        transport = CodexTransport("ws://127.0.0.1:9224", "browzer")
        await transport.connect()
        result = await transport.rpc("getUserTabs")
        await transport.disconnect()
    """

    def __init__(
        self,
        url: str,
        session_id: str,
        rpc_timeout: float = 30.0,
        connect_timeout: float = 10.0,
        max_connect_attempts: int = 5,
    ) -> None:
        self.url = url
        self.session_id = session_id
        self.rpc_timeout = rpc_timeout
        self.connect_timeout = connect_timeout
        self.max_connect_attempts = max_connect_attempts
        self._ws: ClientConnection | None = None
        self._lock = asyncio.Lock()
        self._request_id: int = 0
        self._turn_id: int = 0
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._backoff = INITIAL_BACKOFF

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to the bridge WebSocket and start the reader loop.

        Uses exponential backoff on connection failure, with a finite retry
        limit so MCP startup reports a clear failure instead of hanging forever.
        """
        attempts = 0
        last_error: Exception | None = None
        while attempts < self.max_connect_attempts:
            attempts += 1
            try:
                logger.info("Connecting to Codex bridge at %s", self.url)
                self._ws = await asyncio.wait_for(
                    websockets.connect(self.url), timeout=self.connect_timeout
                )
                self._backoff = INITIAL_BACKOFF
                self._reader_task = asyncio.create_task(self._reader_loop())
                logger.info("Connected to Codex bridge")
                return
            except (OSError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempts >= self.max_connect_attempts:
                    break
                logger.warning(
                    "Bridge connection failed (%s), retrying in %.1fs (%d/%d)",
                    exc,
                    self._backoff,
                    attempts,
                    self.max_connect_attempts,
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(
                    self._backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF
                )

        raise TransportError(
            f"Failed to connect to Codex bridge at {self.url} after "
            f"{self.max_connect_attempts} attempts"
        ) from last_error

    async def disconnect(self) -> None:
        """Close the WebSocket connection and clean up."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        # Fail all pending requests
        async with self._lock:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(
                        TransportError("Transport disconnected")
                    )
            self._pending.clear()

        logger.info("Disconnected from Codex bridge")

    @property
    def connected(self) -> bool:
        """Whether the WebSocket is currently connected."""
        return self._ws is not None

    # ------------------------------------------------------------------
    # RPC
    # ------------------------------------------------------------------

    async def rpc(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict:
        """Send a JSON-RPC request and wait for the response.

        Auto-injects ``session_id`` and ``turn_id`` into params.
        Thread-safe via asyncio.Lock — concurrent callers are
        serialized to avoid request id interleaving.

        Raises:
            TransportError: If the transport is disconnected.
            BridgeError: If the bridge returns a JSON-RPC error.
        """
        async with self._lock:
            if self._ws is None:
                raise TransportError("Not connected to bridge")

            self._request_id += 1
            self._turn_id += 1
            req_id = self._request_id

            if params is None:
                params = {}
            params.setdefault("session_id", self.session_id)
            params.setdefault("turn_id", f"t{self._turn_id}")

            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": req_id,
            }

            fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
            self._pending[req_id] = fut

            try:
                raw = json.dumps(payload)
                await self._ws.send(raw)
                logger.debug("RPC → %s (id=%d)", method, req_id)
            except ConnectionClosed as exc:
                self._pending.pop(req_id, None)
                raise TransportError(f"WebSocket closed: {exc}") from exc

        try:
            result = await asyncio.wait_for(fut, timeout=self.rpc_timeout)
            return result
        except asyncio.TimeoutError as exc:
            logger.warning(
                "RPC %s (id=%d) timed out after %.1fs; resetting bridge connection",
                method,
                req_id,
                self.rpc_timeout,
            )
            async with self._lock:
                self._pending.pop(req_id, None)
            await self.disconnect()
            raise TransportError(
                f"RPC {method} timed out after {self.rpc_timeout:.1f}s"
            ) from exc
        finally:
            async with self._lock:
                self._pending.pop(req_id, None)

    # ------------------------------------------------------------------
    # Reader loop
    # ------------------------------------------------------------------

    async def _reader_loop(self) -> None:
        """Read incoming messages from the WebSocket and dispatch responses."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from bridge: %s", raw[:200])
                    continue

                msg_id = msg.get("id")
                if msg_id is None:
                    logger.debug("Notification from bridge: %s", msg.get("method", "?"))
                    continue

                async with self._lock:
                    fut = self._pending.get(msg_id)

                if fut is None:
                    logger.debug("No pending request for id=%d", msg_id)
                    continue

                if "error" in msg:
                    err = msg["error"]
                    fut.set_exception(
                        BridgeError(
                            code=err.get("code", -1),
                            message=err.get("message", "Unknown bridge error"),
                        )
                    )
                else:
                    fut.set_result(msg.get("result", {}))
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            logger.info("Bridge WebSocket closed by peer")
        except Exception:
            logger.exception("Bridge reader loop crashed")
        finally:
            # Fail all remaining pending requests
            async with self._lock:
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(
                            TransportError("Transport disconnected")
                        )
                self._pending.clear()
            self._ws = None
