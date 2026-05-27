"""Regression tests for tab lifecycle and browser actions."""

import asyncio
import os
import sys
from typing import Any, cast

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browzer.action_engine import ActionEngine
from browzer.element_store import ElementRef, ElementStore
from browzer.tab_manager import TabManager


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.next_tab_id = 123

    async def get_user_tabs(self):
        return []

    async def create_tab(self):
        self.calls.append(("createTab", None))
        return {"id": self.next_tab_id, "url": "about:blank", "title": ""}

    async def claim_user_tab(self, tab_id):
        self.calls.append(("claimUserTab", tab_id))

    async def detach(self, tab_id):
        pass

    async def attach(self, tab_id):
        self.calls.append(("attach", tab_id))

    async def execute_cdp(self, tab_id, method, command_params=None):
        self.calls.append(("executeCdp", tab_id, method, command_params or {}))
        return {"result": {"value": "ok"}}


def test_create_tab_claims_and_attaches_before_navigation():
    bridge = FakeBridge()
    manager = TabManager(cast(Any, bridge))

    asyncio.run(manager.get_or_open_tab("https://example.com", reuse=False))

    ordered = [call[0] if call[0] != "executeCdp" else call[2] for call in bridge.calls]
    assert ordered[:4] == ["createTab", "claimUserTab", "attach", "Page.navigate"]


def test_click_ref_dispatches_mouse_and_dom_click_fallback():
    bridge = FakeBridge()
    store = ElementStore()
    store.set_elements(
        1,
        [
            ElementRef(
                ref="@e1",
                backend_node_id=1,
                tag="input",
                name="size",
                bounds={"x": 10, "y": 20, "width": 30, "height": 40},
            )
        ],
    )
    engine = ActionEngine(cast(Any, bridge), store, state_engine=cast(Any, None))

    result = asyncio.run(engine.click_ref(1, "@e1"))

    assert result.ok is True
    methods = [call[2] for call in bridge.calls if call[0] == "executeCdp"]
    assert methods == [
        "Input.dispatchMouseEvent",
        "Input.dispatchMouseEvent",
        "Runtime.evaluate",
    ]
    dom_click_call = bridge.calls[-1]
    assert "document.elementFromPoint" in dom_click_call[3]["expression"]
    assert ".click()" in dom_click_call[3]["expression"]
