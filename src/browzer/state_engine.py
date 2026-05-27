"""DOM -> indexed page state engine."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from browzer.bridge import CodexBridge
from browzer.element_store import ElementRef, ElementStore
from browzer.tab_manager import TabInfo, TabManager

logger = logging.getLogger(__name__)


@dataclass
class PageState:
    """Structured page state."""

    tab_id: int
    url: str
    title: str
    page_stats: dict[str, int]
    scroll_info: dict[str, float | int]
    elements: list[ElementRef]
    visible_text: str
    tabs: list[TabInfo]


class StateEngine:
    """Builds indexed page state from the browser."""

    def __init__(
        self,
        bridge: CodexBridge,
        element_store: ElementStore,
        tab_manager: TabManager,
    ) -> None:
        self.bridge = bridge
        self.element_store = element_store
        self.tab_manager = tab_manager

    async def build_state(
        self,
        tab_id: int,
        include_tabs: bool = True,
        max_elements: int = 200,
        max_text_chars: int = 8000,
    ) -> PageState:
        """Build full page state for a tab."""
        page_info = await self._get_page_info(tab_id)
        interactive_payload = await self._get_interactive_payload(tab_id)
        visible_text = await self._get_visible_text(tab_id, max_text_chars)
        tabs = await self.tab_manager.list_tabs() if include_tabs else []

        raw_elements = interactive_payload.get("elements", [])
        element_refs: list[ElementRef] = []
        for item in raw_elements[:max_elements]:
            index = self._to_int(item.get("index"), default=len(element_refs) + 1)
            ref = f"@e{index}"
            element_refs.append(
                ElementRef(
                    ref=ref,
                    backend_node_id=self._to_int(item.get("backendNodeId"), 0),
                    node_id=self._maybe_int(item.get("nodeId")),
                    tag=str(item.get("tag", "")),
                    role=str(item.get("role", "")),
                    name=str(item.get("name", "")),
                    text=str(item.get("text", ""))[:100],
                    placeholder=str(item.get("placeholder", "")),
                    value=str(item.get("value", "")),
                    disabled=bool(item.get("disabled", False)),
                    bounds=item.get("bounds") if isinstance(item.get("bounds"), dict) else None,
                )
            )

        self.element_store.set_elements(tab_id, element_refs)

        scroll_y = float(page_info.get("scrollY", 0))
        viewport_h = max(float(page_info.get("innerHeight", 0)), 1.0)
        total_h = max(float(page_info.get("scrollHeight", viewport_h)), viewport_h)
        pages_above = scroll_y / viewport_h
        pages_below = max((total_h - (scroll_y + viewport_h)) / viewport_h, 0.0)

        page_stats = {
            "links": self._to_int(interactive_payload.get("links"), 0),
            "interactive": self._to_int(interactive_payload.get("interactive"), len(raw_elements)),
            "iframes": self._to_int(interactive_payload.get("iframes"), 0),
            "total_elements": self._to_int(interactive_payload.get("total_elements"), 0),
        }

        state = PageState(
            tab_id=tab_id,
            url=str(page_info.get("url", "")),
            title=str(page_info.get("title", "")),
            page_stats=page_stats,
            scroll_info={
                "pages_above": round(pages_above, 1),
                "pages_below": round(pages_below, 1),
                "viewport_height": int(viewport_h),
                "total_height": int(total_h),
            },
            elements=element_refs,
            visible_text=visible_text,
            tabs=tabs,
        )
        logger.debug(
            "Built state for tab %s: %d interactive refs, %d chars text",
            tab_id,
            len(element_refs),
            len(visible_text),
        )
        return state

    async def build_text_state(self, tab_id: int) -> str:
        """Build LLM-friendly text representation of page state."""
        state = await self.build_state(tab_id)
        stats = state.page_stats
        lines = [
            "<page_stats>",
            (
                f'{stats.get("links", 0)} links, {stats.get("interactive", 0)} interactive, '
                f'{stats.get("iframes", 0)} iframe, {stats.get("total_elements", 0)} total elements'
            ),
            "</page_stats>",
            "",
            f"Current tab: {state.tab_id} - {state.url}",
            "Available tabs:",
        ]

        if state.tabs:
            for tab in state.tabs:
                lines.append(f"  {tab.id}: {tab.url} — {tab.title}")
        else:
            lines.append("  (none)")

        scroll = state.scroll_info
        pages_above = float(scroll.get("pages_above", 0.0))
        pages_below = float(scroll.get("pages_below", 0.0))
        hint = "at page boundary"
        if pages_below > 0:
            hint = "scroll down to see more"
        elif pages_above > 0:
            hint = "scroll up to see previous content"

        lines.extend(
            [
                "",
                "<scroll_info>",
                f"{pages_above:.1f} pages above, {pages_below:.1f} pages below — {hint}",
                "</scroll_info>",
                "",
                "Interactive elements:",
            ]
        )

        if state.elements:
            for element in state.elements:
                role = (element.role or element.tag or "element").lower()
                name = (element.name or element.text or element.value or "").strip()
                status = "disabled" if element.disabled else "enabled"
                row = f'{element.ref} [{role}] "{name}"'
                if element.placeholder:
                    row += f' placeholder="{element.placeholder}"'
                row += f" {status}"
                lines.append(row)
        else:
            lines.append("(none)")

        lines.extend(["", "Visible text:", state.visible_text or ""])
        return "\n".join(lines)

    async def build_json_state(self, tab_id: int) -> dict:
        """Build structured JSON page state."""
        state = await self.build_state(tab_id)
        return {
            "tab_id": state.tab_id,
            "url": state.url,
            "title": state.title,
            "page_stats": state.page_stats,
            "scroll_info": state.scroll_info,
            "elements": [
                {
                    "ref": e.ref,
                    "backend_node_id": e.backend_node_id,
                    "node_id": e.node_id,
                    "tag": e.tag,
                    "role": e.role,
                    "name": e.name,
                    "text": e.text,
                    "placeholder": e.placeholder,
                    "value": e.value,
                    "disabled": e.disabled,
                    "bounds": e.bounds,
                }
                for e in state.elements
            ],
            "tabs": [
                {
                    "id": t.id,
                    "url": t.url,
                    "title": t.title,
                    "owned": t.owned,
                    "created": t.created,
                    "attached": t.attached,
                }
                for t in state.tabs
            ],
            "visible_text": state.visible_text,
        }

    async def _get_page_info(self, tab_id: int) -> dict[str, Any]:
        expr = (
            "JSON.stringify({"
            "url: location.href,"
            "title: document.title,"
            "scrollY: window.scrollY,"
            "innerHeight: window.innerHeight,"
            "scrollHeight: document.body ? document.body.scrollHeight : 0"
            "})"
        )
        return await self._evaluate_json(tab_id, expr, fallback={})

    async def _get_interactive_payload(self, tab_id: int) -> dict[str, Any]:
        expr = r"""
JSON.stringify((() => {
  const interactiveRoles = ['button','link','menuitem','option','radio','checkbox','tab','textbox','combobox','slider','spinbutton','searchbox','switch','row','cell','gridcell'];
  const nativeInteractive = ['a','button','input','select','textarea','details','summary'];
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    return r.bottom >= 0 && r.right >= 0 && r.top <= window.innerHeight && r.left <= window.innerWidth;
  };
  const isInteractive = (el) => {
    const tag = (el.tagName || '').toLowerCase();
    if (nativeInteractive.includes(tag)) return true;
    if (el.isContentEditable) return true;
    if (el.hasAttribute('onclick') || el.hasAttribute('onkeydown') || el.hasAttribute('tabindex')) return true;
    const role = (el.getAttribute('role') || '').toLowerCase();
    if (interactiveRoles.includes(role)) return true;
    if (el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby')) return true;
    const style = window.getComputedStyle(el);
    if (style && style.cursor === 'pointer') return true;
    return false;
  };
  const all = Array.from(document.querySelectorAll('body *'));
  const visible = all.filter(isVisible);
  let idx = 1;
  const elements = [];
  for (const el of visible) {
    if (!isInteractive(el)) continue;
    const rect = el.getBoundingClientRect();
    const role = (el.getAttribute('role') || '').toLowerCase();
    const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 100);
    elements.push({
      index: idx++,
      tag: (el.tagName || '').toLowerCase(),
      role: role || '',
      name: (el.getAttribute('aria-label') || el.getAttribute('name') || '').trim(),
      placeholder: (el.getAttribute('placeholder') || '').trim(),
      text,
      value: ((el.value ?? '') + '').slice(0, 200),
      disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
      bounds: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      backendNodeId: Number(el.getAttribute('data-backend-node-id') || 0),
      nodeId: Number(el.getAttribute('data-node-id') || 0)
    });
  }
  return {
    links: visible.filter(el => (el.tagName || '').toLowerCase() === 'a').length,
    interactive: elements.length,
    iframes: visible.filter(el => (el.tagName || '').toLowerCase() === 'iframe').length,
    total_elements: visible.length,
    elements
  };
})())
"""
        payload = await self._evaluate_json(tab_id, expr, fallback={})
        if not isinstance(payload, dict):
            return {"links": 0, "interactive": 0, "iframes": 0, "total_elements": 0, "elements": []}
        payload.setdefault("elements", [])
        return payload

    async def _get_visible_text(self, tab_id: int, max_chars: int) -> str:
        expr = (
            "(() => {"
            "const t = (document.body && document.body.innerText) ? document.body.innerText : '';"
            "return t.slice(0, "
            f"{int(max_chars)}"
            ");"
            "})()"
        )
        value = await self._evaluate_value(tab_id, expr, fallback="")
        return str(value or "")[:max_chars]

    async def _evaluate_json(self, tab_id: int, expression: str, fallback: Any) -> Any:
        value = await self._evaluate_value(tab_id, expression, fallback="")
        if not isinstance(value, str):
            return fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.debug("Failed to decode JSON from Runtime.evaluate")
            return fallback

    async def _evaluate_value(self, tab_id: int, expression: str, fallback: Any) -> Any:
        response = await self.bridge.execute_cdp(
            tab_id,
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
        try:
            return response["result"]["result"]["value"]
        except Exception:
            pass
        try:
            return response["result"]["value"]
        except Exception:
            pass
        try:
            return response["value"]
        except Exception:
            pass
        return fallback

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _maybe_int(value: Any) -> int | None:
        try:
            v = int(value)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
