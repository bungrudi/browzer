"""Execute browser actions (click, fill, scroll) by element ref."""

import asyncio
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
        element = self.element_store.get_element(tab_id, ref)
        bounds = element.bounds if element else None
        if not bounds:
            return ActionResult(
                ok=False,
                action="click",
                ref=ref,
                details="Element not found or missing bounds",
            )

        try:
            x = float(bounds.get("x", 0)) + (float(bounds.get("width", 0)) / 2)
            y = float(bounds.get("y", 0)) + (float(bounds.get("height", 0)) / 2)
            await self.bridge.execute_cdp(
                tab_id,
                "Input.dispatchMouseEvent",
                {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
            )
            await self.bridge.execute_cdp(
                tab_id,
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
            )
            # The Codex bridge may report mouse dispatch success without the
            # page applying the click (observed on native inputs). Trigger a
            # DOM click at the same coordinate as a deterministic fallback.
            await self.bridge.execute_cdp(
                tab_id,
                "Runtime.evaluate",
                {
                    "expression": (
                        "((x, y) => {"
                        "const el = document.elementFromPoint(x, y);"
                        "if (!el) return 'element_not_found';"
                        "el.click();"
                        "return (el.tagName || '').toLowerCase();"
                        f"}})({x}, {y})"
                    ),
                    "returnByValue": True,
                },
            )
            await asyncio.sleep(0.5)
            return ActionResult(
                ok=True,
                action="click",
                ref=ref,
                details=f"Clicked at ({x:.1f}, {y:.1f})",
                state_delta={"action": "click", "ref": ref},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="click",
                ref=ref,
                details=f"Click failed: {exc}",
            )

    async def fill_ref(
        self, tab_id: int, ref: str, text: str, submit: bool = False
    ) -> ActionResult:
        """Fill an input element by ref. Optionally submit (Enter)."""
        element = self.element_store.get_element(tab_id, ref)
        bounds = element.bounds if element else None
        if not bounds:
            return ActionResult(
                ok=False,
                action="fill",
                ref=ref,
                details="Element not found or missing bounds",
            )

        x = float(bounds.get("x", 0)) + (float(bounds.get("width", 0)) / 2)
        y = float(bounds.get("y", 0)) + (float(bounds.get("height", 0)) / 2)

        expr = r"""
((x, y, text, submit) => {
    const el = document.elementFromPoint(x, y);
    if (!el) return "element_not_found";
    el.focus();
    if (el.isContentEditable) {
        el.textContent = text;
        el.dispatchEvent(new InputEvent("input", {bubbles:true, inputType:"insertText", data:text}));
    } else {
        if (el instanceof HTMLTextAreaElement) {
            const nativeTextareaValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
            nativeTextareaValueSetter.call(el, text);
        } else {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(el, text);
        }
        el.dispatchEvent(new Event("input", {bubbles:true}));
        el.dispatchEvent(new Event("change", {bubbles:true}));
    }
    if (submit) {
        el.dispatchEvent(new KeyboardEvent("keydown", {key:"Enter", code:"Enter", keyCode:13, bubbles:true}));
        setTimeout(() => el.dispatchEvent(new KeyboardEvent("keyup", {key:"Enter", bubbles:true})), 50);
    }
    return "ok";
})(%s, %s, %s, %s)
""" % (x, y, repr(text), "true" if submit else "false")

        try:
            await self.bridge.execute_cdp(
                tab_id,
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True},
            )
            await asyncio.sleep(0.25)
            return ActionResult(
                ok=True,
                action="fill",
                ref=ref,
                details="Filled element",
                state_delta={
                    "action": "fill",
                    "ref": ref,
                    "text": text,
                    "submit": submit,
                },
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="fill",
                ref=ref,
                details=f"Fill failed: {exc}",
            )

    async def scroll(
        self, tab_id: int, direction: str = "down", pages: float = 1.0
    ) -> ActionResult:
        """Scroll the page by a number of viewport-pages."""
        sign = 1 if direction.lower() == "down" else -1
        try:
            expr = (
                "JSON.stringify((() => {"
                f"const delta = {sign * pages} * window.innerHeight;"
                "window.scrollBy(0, delta);"
                "return {direction: delta >= 0 ? 'down' : 'up', pages: Math.abs(delta / window.innerHeight), deltaY: delta, scrollY: window.scrollY};"
                "})())"
            )
            result = await self.bridge.execute_cdp(
                tab_id,
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True},
            )
            value = result.get("result", {}).get("value")
            state_delta = {
                "action": "scroll",
                "direction": direction,
                "pages": pages,
            }
            if isinstance(value, str):
                state_delta["scroll_info"] = value
            return ActionResult(
                ok=True,
                action="scroll",
                details=f"Scrolled {direction} by {pages} page(s)",
                state_delta=state_delta,
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="scroll",
                details=f"Scroll failed: {exc}",
            )

    async def press_key(self, tab_id: int, key: str) -> ActionResult:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        key_map = {
            "Enter": {"key": "Enter", "code": "Enter", "keyCode": 13},
            "Tab": {"key": "Tab", "code": "Tab", "keyCode": 9},
            "Escape": {"key": "Escape", "code": "Escape", "keyCode": 27},
            "ArrowDown": {"key": "ArrowDown", "code": "ArrowDown", "keyCode": 40},
            "ArrowUp": {"key": "ArrowUp", "code": "ArrowUp", "keyCode": 38},
        }
        if key not in key_map:
            return ActionResult(
                ok=False,
                action="press_key",
                details=f"Unsupported key: {key}",
            )

        params = key_map[key]
        payload = {
            "key": params["key"],
            "code": params["code"],
            "windowsVirtualKeyCode": params["keyCode"],
            "nativeVirtualKeyCode": params["keyCode"],
        }

        try:
            await self.bridge.execute_cdp(
                tab_id,
                "Input.dispatchKeyEvent",
                {"type": "keyDown", **payload},
            )
            await self.bridge.execute_cdp(
                tab_id,
                "Input.dispatchKeyEvent",
                {"type": "keyUp", **payload},
            )
            return ActionResult(
                ok=True,
                action="press_key",
                details=f"Pressed {key}",
                state_delta={"action": "press_key", "key": key},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="press_key",
                details=f"Key press failed: {exc}",
            )
