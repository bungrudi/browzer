"""Regression tests for bridge transport timeout handling."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from browzer.transport import CodexTransport, TransportError


class SilentWebSocket:
    """Fake WebSocket that accepts sends but never produces responses."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, raw: str):
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True


def test_rpc_times_out_and_cleans_pending_request_when_bridge_never_replies():
    async def scenario():
        websocket = SilentWebSocket()
        transport = CodexTransport(
            "ws://bridge.example", "test-session", rpc_timeout=0.01
        )
        transport._ws = websocket

        with pytest.raises(TransportError, match="neverResponds.*timed out"):
            await transport.rpc("neverResponds")

        assert transport._pending == {}
        assert websocket.closed is True
        assert transport.connected is False
        assert websocket.sent[0]["method"] == "neverResponds"
        assert websocket.sent[0]["params"]["session_id"] == "test-session"

    asyncio.run(scenario())
