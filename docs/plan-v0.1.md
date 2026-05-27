# Browzer v0.1 — Implementation Plan

## Overview

Implement Browzer as a Python MCP server (FastMCP) in 9 tasks, each delegated to Codex CLI (gpt-5.3-codex). Hermes (deepseek-v4-pro) plans and reviews; Codex writes code, runs tests.

## Architecture Recap

```
MCP Client (Hermes) ──stdio──▶ Browzer Server (server.py)
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              State Engine    Action Engine    Vision Layer
              (state_engine)  (action_engine)  (vision/)
                    │               │               │
                    └───────┬───────┘               │
                            │                       │
                      Element Store         Vision LLM Client
                      (element_store)       (vision/client.py)
                            │
                      Tab Manager
                      (tab_manager)
                            │
                      Transport Layer
                      (transport.py, bridge.py)
                            │
                  WebSocket :9224 ──▶ Codex Chrome Extension
```

## Data Flow

1. MCP tool call arrives → server.py
2. server.py delegates to state_engine, action_engine, or vision layer
3. State engine queries transport layer (executeCdp → Runtime.evaluate / Accessibility.getFullAXTree)
4. Results stored in element_store (ref → backendNodeId mapping)
5. Action engine resolves refs through element_store, sends CDP commands via transport
6. Vision layer captures screenshots via CDP, sends to configurable vision LLM

---

## Task 1: Project Scaffolding + Config

**Files to create:**
- `pyproject.toml` — project metadata, deps, scripts entry point
- `src/browzer/__init__.py` — `__version__`
- `src/browzer/config.py` — env/config loading

**pyproject.toml spec:**
```toml
[project]
name = "browzer"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "websockets>=12",
    "mcp>=1.0",
    "httpx>=0.27",
    "openai>=1.0",
]

[project.scripts]
browzer = "browzer.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/browzer"]
```

**config.py spec:**
```python
"""Configuration from environment variables."""
import os
from dataclasses import dataclass, field

@dataclass
class BrowzerConfig:
    # Codex bridge
    bridge_url: str = "ws://127.0.0.1:9224"
    bridge_session_id: str = "browzer"
    
    # Vision LLM
    vision_base_url: str = "http://127.0.0.1:2455/v1"
    vision_model: str = "gemini-2.5-flash-lite"
    vision_api_key: str = ""
    vision_max_tokens: int = 1024
    vision_temperature: float = 0.0
    vision_timeout: int = 30
    
    # Drive mode: "mediated" (vision-enriched text) or "vision" (vision-first)
    drive_mode: str = "mediated"
    
    # Screenshot
    screenshot_quality: int = 80
    screenshot_width: int | None = None  # None = viewport width
    
    # Session
    session_timeout: int = 300

    @classmethod
    def from_env(cls) -> "BrowzerConfig":
        return cls(
            bridge_url=os.getenv("CODEX_CHROME_BRIDGE_URL", "ws://127.0.0.1:9224"),
            bridge_session_id=os.getenv("BROWZER_SESSION_ID", "browzer"),
            vision_base_url=os.getenv("BROWZER_VISION_BASE_URL", "http://127.0.0.1:2455/v1"),
            vision_model=os.getenv("BROWZER_VISION_MODEL", "gemini-2.5-flash-lite"),
            vision_api_key=os.getenv("BROWZER_VISION_API_KEY", ""),
            vision_max_tokens=int(os.getenv("BROWZER_VISION_MAX_TOKENS", "1024")),
            vision_temperature=float(os.getenv("BROWZER_VISION_TEMPERATURE", "0")),
            vision_timeout=int(os.getenv("BROWZER_VISION_TIMEOUT", "30")),
            drive_mode=os.getenv("BROWZER_DRIVE_MODE", "mediated"),
            screenshot_quality=int(os.getenv("BROWZER_SCREENSHOT_QUALITY", "80")),
            screenshot_width=(
                int(w) if (w := os.getenv("BROWZER_SCREENSHOT_WIDTH")) else None
            ),
            session_timeout=int(os.getenv("BROWZER_SESSION_TIMEOUT", "300")),
        )
```

**Also create empty stub files:**
- `src/browzer/bridge.py` — `# Transport: Codex bridge client`
- `src/browzer/transport.py` — `# Transport: WebSocket JSON-RPC`
- `src/browzer/tab_manager.py` — `# Tab lifecycle management`
- `src/browzer/element_store.py` — `# Ref ↔ backendNodeId mapping`
- `src/browzer/state_engine.py` — `# DOM → indexed page state`
- `src/browzer/action_engine.py` — `# Click, fill, scroll by ref`
- `src/browzer/vision/__init__.py` — empty
- `src/browzer/vision/client.py` — `# Vision LLM client`
- `src/browzer/vision/observe.py` — `# Screenshot + vision LLM`
- `src/browzer/server.py` — `# FastMCP server`

---

## Task 2: Transport Layer (bridge.py + transport.py)

**Goal:** WebSocket client for the Codex Chrome extension bridge on port 9224.

**Files:**
- `src/browzer/transport.py` — Low-level WebSocket JSON-RPC client
- `src/browzer/bridge.py` — High-level Codex bridge methods

### transport.py — `CodexTransport`

```python
class CodexTransport:
    """Low-level WebSocket JSON-RPC client for the Codex bridge."""
    
    def __init__(self, url: str, session_id: str):
        self.url = url
        self.session_id = session_id
        self._ws: WebSocket | None = None
        self._request_id: int = 0
        self._lock: asyncio.Lock
    
    async def connect(self) -> None:
        """Connect WebSocket. Uses exponential backoff on failure."""
    
    async def disconnect(self) -> None:
        """Close WebSocket gracefully."""
    
    async def rpc(self, method: str, params: dict | None = None) -> dict:
        """Send JSON-RPC request, await response. Thread-safe via lock."""
        # 1. Increment _request_id
        # 2. Send: {"jsonrpc":"2.0","method":"...","params":{...},"id":N}
        #    Auto-inject session_id and turn_id into params
        # 3. Read until matching id response arrives
        # 4. Raise BridgeError on error response
        # 5. Return result
    
    @property
    def connected(self) -> bool:
        """Whether WebSocket is open."""
```

**Key behavior:**
- `rpc()` auto-injects `session_id` and `turn_id` into params
- `turn_id` = auto-incrementing counter per call (e.g., `"t1"`, `"t2"`)
- Thread-safe: uses asyncio.Lock so concurrent callers don't interleave
- Raises `BridgeError(code, message)` on JSON-RPC error responses
- Auto-reconnect: if WebSocket drops, `rpc()` triggers reconnect with backoff (1s → 2s → 4s → max 30s)

### bridge.py — `CodexBridge`

```python
class CodexBridge:
    """High-level Codex Chrome bridge operations."""
    
    def __init__(self, transport: CodexTransport):
        self.transport = transport
    
    async def get_user_tabs(self) -> list[dict]:
        """List all open user tabs. Returns [{id, title, url, ...}]."""
    
    async def create_tab(self) -> dict:
        """Create a new blank tab. Returns {id, title, url, active}."""
    
    async def claim_user_tab(self, tab_id: int) -> None:
        """Claim ownership of a tab for CDP."""
    
    async def attach(self, tab_id: int) -> None:
        """Attach debugger to a tab."""
    
    async def detach(self, tab_id: int) -> None:
        """Detach debugger from a tab."""
    
    async def execute_cdp(self, tab_id: int, method: str, command_params: dict | None = None) -> dict:
        """Execute a raw CDP command on a tab.
        Examples:
          Page.navigate → {"url": "https://..."}
          Runtime.evaluate → {"expression": "...", "returnByValue": True}
          Page.captureScreenshot → {"format": "png"}
          Accessibility.getFullAXTree → {}
        """
    
    async def get_info(self) -> dict:
        """Get extension info."""
```

**execute_cdp detail:**
```python
async def execute_cdp(self, tab_id: int, method: str, command_params=None):
    return await self.transport.rpc("executeCdp", {
        "target": {"tabId": tab_id},
        "method": method,
        "commandParams": command_params or {},
    })
```

**Error handling:** Define `BridgeError(Exception)` with `code` and `message` attributes.

---

## Task 3: Tab Manager (tab_manager.py)

**Goal:** Track tab lifecycle — creation, claiming, reuse, cleanup.

### TabManager

```python
@dataclass
class TabInfo:
    id: int
    url: str = ""
    title: str = ""
    owned: bool = False   # claimed by us
    created: bool = False  # created by us
    attached: bool = False

class TabManager:
    def __init__(self, bridge: CodexBridge):
        self.bridge = bridge
        self._tabs: dict[int, TabInfo] = {}
    
    async def list_tabs(self) -> list[TabInfo]:
        """Refresh from bridge.get_user_tabs(), merge with _tabs."""
    
    async def find_tab(self, url: str = "", url_contains: str = "", 
                       title_contains: str = "") -> TabInfo | None:
        """Find best matching existing tab. Priority: exact URL > URL contains > title contains."""
    
    async def get_or_open_tab(self, url: str, reuse: bool = True) -> TabInfo:
        """Reuse-first policy:
        1. If reuse=True, call find_tab(url, url_contains=domain)
        2. If found, claim + attach if not already, return it
        3. If not found, create_tab → navigate → claim → attach
        4. Track as owned+created
        """
    
    async def create_tab(self, url: str) -> TabInfo:
        """Create tab, navigate, claim, attach. Mark as created+owned."""
    
    async def claim_and_attach(self, tab_id: int) -> None:
        """claimUserTab + attach. Idempotent (skip if already attached)."""
    
    async def close_tab(self, tab_id: int) -> bool:
        """Close a tab via CDP. Only closes owned tabs. Returns success."""
    
    async def cleanup(self, keep_tab_id: int | None = None, 
                      dry_run: bool = True) -> dict:
        """Find and optionally close unused owned tabs.
        Returns {dry_run, candidates: [TabInfo], closed: [int]}
        Candidates: owned tabs that are blank or not the keep_tab_id.
        """
    
    async def navigate(self, tab_id: int, url: str) -> None:
        """Navigate existing tab to URL."""
```

**Reuse logic detail:**
1. Extract domain from URL (e.g., `gemini.google.com` from `https://gemini.google.com/app`)
2. `find_tab()`: first exact URL match → domain match → title match
3. On match: claim + attach (idempotent)
4. Fallback: create new tab, navigate, claim, attach

**Cleanup logic:**
- Candidates = owned tabs where:
  - URL is blank/empty/about:blank
  - OR tab is NOT the keep_tab_id
- Never close tabs not owned by Browzer
- dry_run=True only lists candidates, doesn't close

---

## Task 4: Element Store (element_store.py)

**Goal:** Maintain ref ↔ backendNodeId mapping per tab. Resolve refs to CDP node IDs.

### ElementStore

```python
@dataclass
class ElementRef:
    """An indexed element reference."""
    ref: str           # "@e1", "@e2", ...
    backend_node_id: int
    node_id: int | None  # DOM nodeId (runtime)
    tag: str
    role: str
    name: str = ""
    text: str = ""
    placeholder: str = ""
    value: str = ""
    disabled: bool = False
    bounds: dict | None = None  # {x, y, width, height}
    attributes: dict = field(default_factory=dict)

class ElementStore:
    def __init__(self):
        self._stores: dict[int, dict[str, ElementRef]] = {}  # tab_id → {ref → ElementRef}
    
    def set_elements(self, tab_id: int, elements: list[ElementRef]) -> None:
        """Store indexed elements for a tab. Overwrites previous."""
        self._stores[tab_id] = {e.ref: e for e in elements}
    
    def get_element(self, tab_id: int, ref: str) -> ElementRef | None:
        """Resolve a ref to its ElementRef."""
        store = self._stores.get(tab_id, {})
        return store.get(ref)
    
    def invalidate(self, tab_id: int) -> None:
        """Clear stored elements for a tab (page changed)."""
        self._stores.pop(tab_id, None)
    
    def list_refs(self, tab_id: int) -> list[str]:
        """List all refs for a tab."""
        return list(self._stores.get(tab_id, {}).keys())
```

**Ref format:** `@e1`, `@e2`, ... — sequential 1-based indices assigned by state_engine.

---

## Task 5: State Engine (state_engine.py)

**Goal:** Build the compact, indexed page state from DOM + accessibility tree.

### StateEngine

Uses CDP to query the page and produces two output formats:
1. **Text format** (for LLM consumption in prompts)
2. **JSON format** (structured, for programmatic consumers)

```python
@dataclass
class PageState:
    """Structured page state."""
    tab_id: int
    url: str
    title: str
    page_stats: dict       # {links, interactive, iframes, total_elements}
    scroll_info: dict      # {pages_above, pages_below, total_height, viewport_height}
    elements: list[ElementRef]
    visible_text: str      # truncated visible text content
    tabs: list[TabInfo]    # all open tabs

class StateEngine:
    def __init__(self, bridge: CodexBridge, element_store: ElementStore, tab_manager: TabManager):
        ...
    
    async def build_state(self, tab_id: int, 
                          include_tabs: bool = True,
                          max_elements: int = 200,
                          max_text_chars: int = 8000) -> PageState:
        """Build full page state for a tab."""
    
    async def build_text_state(self, tab_id: int) -> str:
        """Build the LLM-friendly text format (per PRD spec)."""
    
    async def build_json_state(self, tab_id: int) -> dict:
        """Build structured JSON state."""
```

### State Building Pipeline

1. **Get page info** — `Runtime.evaluate("JSON.stringify({url:location.href, title:document.title, scrollY:window.scrollY, innerHeight:window.innerHeight, scrollHeight:document.body.scrollHeight})")`
2. **Get interactive elements** — Use `Runtime.evaluate()` with a JavaScript function that:
   - Walks all visible elements in the DOM
   - Checks interactivity using browser-use heuristics (see below)
   - Assigns sequential indices (1-based)
   - Returns array of `{index, tag, role, name, placeholder, text, disabled, bounds, backendNodeId?}`
3. **Get visible text** — `Runtime.evaluate()` to extract `document.body.innerText`, truncate
4. **Get tabs** — `tab_manager.list_tabs()`
5. **Build ElementRefs** — Create `ElementRef` objects from JS results, store in element_store
6. **Calculate scroll_info** — from scrollY, innerHeight, scrollHeight
7. **Count stats** — count links, interactive elements, iframes, total elements

### Interactive Element Detection (JS implementation)

The JS function injected into the page must detect interactive elements:

```javascript
function isInteractive(el) {
    const tag = el.tagName.toLowerCase();
    const nativeInteractive = ['a','button','input','select','textarea','details','summary'];
    if (nativeInteractive.includes(tag)) return true;
    if (el.isContentEditable) return true;
    if (el.hasAttribute('onclick') || el.hasAttribute('onkeydown') || el.hasAttribute('tabindex')) return true;
    const role = (el.getAttribute('role') || '').toLowerCase();
    const interactiveRoles = ['button','link','menuitem','option','radio','checkbox','tab',
        'textbox','combobox','slider','spinbutton','searchbox','switch','row','cell','gridcell'];
    if (interactiveRoles.includes(role)) return true;
    if (el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby')) return true;
    const style = getComputedStyle(el);
    if (style.cursor === 'pointer') return true;
    return false;
}
```

### Text State Output Format

```
<page_stats>
12 links, 7 interactive, 1 iframe, 98 total elements
</page_stats>

Current tab: 1292176900 - https://gemini.google.com
Available tabs:
  1292176900: https://gemini.google.com — Google Gemini
  1292176500: https://github.com — GitHub

<scroll_info>
0.0 pages above, 1.2 pages below — scroll down to see more
</scroll_info>

Interactive elements:
@e1 [textbox] "Ask Gemini" placeholder="Ask Gemini" enabled
@e2 [button] "Send message" disabled
@e3 [button] "New chat" enabled
@e4 [link] "Terms of Service"

Visible text:
Gemini
Conversation with Gemini
...
```

---

## Task 6: Action Engine (action_engine.py)

**Goal:** Execute browser actions (click, fill, scroll) by element ref.

### ActionEngine

```python
@dataclass
class ActionResult:
    ok: bool
    action: str            # "click", "fill", "scroll"
    ref: str | None = None
    details: str = ""
    state_delta: dict | None = None  # what changed

class ActionEngine:
    def __init__(self, bridge: CodexBridge, element_store: ElementStore, 
                 state_engine: StateEngine):
        ...
    
    async def click_ref(self, tab_id: int, ref: str) -> ActionResult:
        """Click element by ref.
        1. Resolve ref → ElementRef from element_store
        2. Get center coordinates from bounds
        3. Execute CDP: Input.dispatchMouseEvent (mousePressed + mouseReleased)
        4. Wait 500ms for page updates
        5. Build state_delta by diffing elements
        """
    
    async def fill_ref(self, tab_id: int, ref: str, text: str, 
                       submit: bool = False) -> ActionResult:
        """Fill input by ref.
        1. Resolve ref → ElementRef
        2. Focus element via Runtime.evaluate: el.focus()
        3. Set value + dispatch input events via Runtime.evaluate (SPA-friendly):
           - For contenteditable: el.textContent = text; dispatch InputEvent('input')
           - For input/textarea: el.value = text; dispatch Event('input')
        4. If submit=True, dispatch Enter key: KeyboardEvent('keydown',{key:'Enter'})
        5. Wait 250ms for updates
        6. Build state_delta
        """
    
    async def scroll(self, tab_id: int, direction: str = "down", 
                     pages: float = 1.0) -> ActionResult:
        """Scroll page.
        1. Calculate pixels: pages * viewport_height
        2. Runtime.evaluate: window.scrollBy(0, +/-pixels)
        3. Return new scroll_info as state_delta
        """
    
    async def press_key(self, tab_id: int, key: str) -> ActionResult:
        """Press a key on the page.
        Useful for Enter, Tab, Escape, etc.
        """
    
    def _build_state_delta(self, old_elements, new_elements) -> dict:
        """Compare old and new element lists, return {added[], removed[], changed[]}."""
```

### Click Implementation Detail

```python
async def click_ref(self, tab_id, ref):
    el = self.element_store.get_element(tab_id, ref)
    if not el or not el.bounds:
        return ActionResult(ok=False, ref=ref, details="Element not found or no bounds")
    
    x = el.bounds["x"] + el.bounds["width"] / 2
    y = el.bounds["y"] + el.bounds["height"] / 2
    
    # mousePressed
    await self.bridge.execute_cdp(tab_id, "Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1
    })
    # mouseReleased
    await self.bridge.execute_cdp(tab_id, "Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1
    })
    
    await asyncio.sleep(0.5)
    # Refresh state
    ...
```

### Fill Implementation Detail (SPA-friendly)

```javascript
// Execute in page context
(el, text, submit) => {
    el.focus();
    if (el.isContentEditable) {
        el.textContent = text;
        el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: text}));
    } else {
        // Check if it's a CodeMirror or custom editor
        const nativeInputTypes = new Set(['text','email','password','search','url','tel','number']);
        if (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && nativeInputTypes.has(el.type))) {
            // For native inputs, set value + trigger React/Angular change detection
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(el, text);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        } else {
            el.value = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }
    if (submit) {
        el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
        setTimeout(() => el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', bubbles: true})), 50);
    }
}
```

---

## Task 7: Vision Layer (vision/)

**Goal:** Screenshot capture + configurable vision LLM for page observation.

### vision/client.py — VisionClient

```python
class VisionClient:
    """OpenAI-compatible vision API client."""
    
    def __init__(self, config: BrowzerConfig):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            base_url=config.vision_base_url,
            api_key=config.vision_api_key or "not-needed",
        )
        self.model = config.vision_model
        self.max_tokens = config.vision_max_tokens
        self.temperature = config.vision_temperature
        self.timeout = config.vision_timeout
    
    async def describe(self, image_base64: str, instruction: str,
                       system_prompt: str | None = None) -> str:
        """Send image + instruction to vision LLM, get text description."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                {"type": "text", "text": instruction},
            ]
        })
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content
```

### vision/observe.py — observe()

```python
DEFAULT_SYSTEM_PROMPT = """You are a browser page observer. Given a screenshot and an instruction, describe what you see. Focus on:
1. The overall page layout and structure
2. Visible interactive elements (buttons, inputs, links) with their positions
3. Key text content and headings
4. Any form fields, their labels, and current values
5. Navigation elements (menus, tabs, sidebars)
Be concise. Use relative positions (top-left, center, bottom-right, etc.).
"""

async def capture_screenshot(bridge: CodexBridge, tab_id: int, 
                             quality: int = 80) -> str:
    """Capture a screenshot of a tab. Returns base64 PNG string."""
    result = await bridge.execute_cdp(tab_id, "Page.captureScreenshot", {
        "format": "png",
        "quality": quality,
    })
    return result["data"]

async def observe(bridge: CodexBridge, vision_client: VisionClient,
                  tab_id: int, instruction: str,
                  system_prompt: str | None = None) -> dict:
    """Observe a page: capture screenshot + send to vision LLM.
    Returns {ok, observations: str, state_snapshot: PageState | None}
    """
    screenshot_b64 = await capture_screenshot(bridge, tab_id)
    description = await vision_client.describe(
        screenshot_b64, instruction, 
        system_prompt or DEFAULT_SYSTEM_PROMPT
    )
    return {"ok": True, "observations": description, "state_snapshot": None}
```

---

## Task 8: MCP Server (server.py)

**Goal:** FastMCP server registering all v0.1 tools. The entry point.

### Tools to Register

All tools share a `BrowzerSession` context that holds the bridge, tab_manager, element_store, state_engine, action_engine, and vision_client.

```python
@dataclass
class BrowzerSession:
    config: BrowzerConfig
    transport: CodexTransport
    bridge: CodexBridge
    tab_manager: TabManager
    element_store: ElementStore
    state_engine: StateEngine
    action_engine: ActionEngine
    vision_client: VisionClient | None
```

**Tool implementations:**

1. `browser_start(url, mode="text", reuse=True)` → `{tab_id, reused, url, title}`
   - Calls `tab_manager.get_or_open_tab(url, reuse)`
   - Returns tab info

2. `browser_state(tab_id, format="text")` → text or JSON state
   - Calls `state_engine.build_state(tab_id)` or `build_text_state(tab_id)`
   - Returns the formatted state

3. `browser_observe(tab_id, instruction, system_prompt=None)` → `{ok, observations}`
   - Calls `vision/observe.py:observe(...)`
   - Requires vision_client configured

4. `browser_click_ref(tab_id, ref)` → `{ok, ref, state_delta}`
   - Calls `action_engine.click_ref(tab_id, ref)`
   - Returns result + state_delta

5. `browser_fill_ref(tab_id, ref, text, submit=False)` → `{ok, ref, text, submitted, state_delta}`
   - Calls `action_engine.fill_ref(tab_id, ref, text, submit)`

6. `browser_scroll(tab_id, direction="down", pages=1.0)` → `{ok, scroll_info}`
   - Calls `action_engine.scroll(tab_id, direction, pages)`

7. `browser_switch_tab(tab_id)` → `{ok, state}`
   - Calls `tab_manager.claim_and_attach(tab_id)`
   - Returns state of new tab

8. `browser_close_tab(tab_id)` → `{ok, closed}`
   - Only for owned tabs
   
9. `browser_cleanup(keep_tab_id=None, dry_run=True)` → `{dry_run, candidates, closed}`
   - Calls `tab_manager.cleanup(keep_tab_id, dry_run)`

10. `browser_eval(tab_id, expression)` → `{result}`
    - `bridge.execute_cdp(tab_id, "Runtime.evaluate", {"expression": expression, "returnByValue": true})`

### Server Entry Point

```python
def main():
    """Entry point for 'browzer' command and 'python -m browzer'."""
    import asyncio
    from mcp.server.fastmcp import FastMCP
    
    config = BrowzerConfig.from_env()
    mcp = FastMCP("browzer")
    
    # Create session on startup
    session: BrowzerSession = None
    
    @mcp.lifespan
    async def lifespan(server):
        nonlocal session
        transport = CodexTransport(config.bridge_url, config.bridge_session_id)
        await transport.connect()
        bridge = CodexBridge(transport)
        tab_manager = TabManager(bridge)
        element_store = ElementStore()
        state_engine = StateEngine(bridge, element_store, tab_manager)
        action_engine = ActionEngine(bridge, element_store, state_engine)
        vision_client = None
        if config.vision_api_key or "not-needed":
            vision_client = VisionClient(config)
        session = BrowzerSession(
            config=config, transport=transport, bridge=bridge,
            tab_manager=tab_manager, element_store=element_store,
            state_engine=state_engine, action_engine=action_engine,
            vision_client=vision_client,
        )
        yield
        await transport.disconnect()
    
    # Register all tools (each function uses session from lifespan)
    # ... register browser_start, browser_state, etc.
    
    mcp.run()
```

### Tool Registration Pattern

```python
@mcp.tool()
async def browser_start(url: str, mode: str = "text", reuse: bool = True) -> dict:
    """Open or reuse a tab. Returns tab_id and initial state."""
    tab = await session.tab_manager.get_or_open_tab(url, reuse=reuse)
    return {"tab_id": tab.id, "reused": not tab.created, "url": tab.url, "title": tab.title}
```

---

## Task 9: Integration, Tests, Examples

**Goal:** Make the project runnable end-to-end, create Hermes config example.

**Files:**
- `tests/test_bridge.py` — Unit tests for transport/bridge (mock WebSocket)
- `tests/test_tab_manager.py` — Unit tests for tab manager
- `tests/test_element_store.py` — Unit tests for element store
- `tests/test_config.py` — Config loading tests
- `examples/hermes-config.yaml` — Example Hermes MCP configuration
- `README.md` — Usage instructions

### Hermes Config Example

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  browzer:
    command: /home/rudi/Workspace/browzer/.venv/bin/python
    args:
      - -m
      - browzer
    timeout: 120
```

### Environment Setup

```bash
# Required: Codex Chrome bridge must be running
# Check: ss -tlnp | grep 9224

# Optional: Vision LLM
export BROWZER_VISION_BASE_URL=http://127.0.0.1:2455/v1
export BROWZER_VISION_MODEL=gemini-2.5-flash-lite
export BROWZER_VISION_API_KEY=sk-xxx
```

### README.md Sections
- What is Browzer
- Quick start (3 steps: venv, deps, Hermes config)
- Configuration reference
- Tool API reference
- Architecture overview
- Comparison with alternatives

---

## Execution Order

Tasks must execute sequentially because each builds on the previous:

1. **Task 1**: Scaffolding → pyproject.toml, config.py, stub files
2. **Task 2**: Transport → bridge.py, transport.py (foundational: all other layers depend on it)
3. **Task 3**: Tab Manager → tab_manager.py (depends on transport)
4. **Task 4**: Element Store → element_store.py (no deps beyond Python)
5. **Task 5**: State Engine → state_engine.py (depends on transport, element_store, tab_manager)
6. **Task 6**: Action Engine → action_engine.py (depends on transport, element_store, state_engine)
7. **Task 7**: Vision Layer → vision/ (depends on transport)
8. **Task 8**: MCP Server → server.py (depends on all above)
9. **Task 9**: Tests, examples, README

## Verification Per Task

After each task, Codex must:
1. Run any new tests it added
2. Verify imports work: `.venv/bin/python -c "from browzer.X import Y"`
3. Return a git commit with a descriptive message
