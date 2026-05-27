# Browzer — Product Requirements Document

## Overview

**Browzer** is an MCP (Model Context Protocol) server that gives AI agents a semantic, text-first, vision-augmented interface to an existing Chrome browser. It connects to Chrome through the Codex Chrome extension native host bridge and presents the page as structured, indexed, LLM-friendly state. Vision-capable models can drive the browser directly via screenshots; non-vision models receive vision-enriched text descriptions and interact through stable element references.

Browzer is designed as a drop-in MCP server for Hermes Agent. The user clones the repo, creates a venv, adds it to `~/.hermes/config.yaml`, and Hermes gains semantic browser tools.

**Repo:** https://github.com/bungrudi/browzer

---

## Problem Statement

Non-vision LLMs (e.g., DeepSeek v4) struggle with browser automation because:

1. **Raw DOM is too noisy** — a typical SPA page has thousands of nodes. Models drown in irrelevant markup.
2. **No screenshot/pixel understanding** — non-vision models cannot "see" where buttons are, what a page layout looks like, or read canvas-based content.
3. **Selector fragility** — asking models to invent CSS selectors or XPaths is unreliable and brittle.
4. **No stable interaction model** — low-level CDP commands are verbose and error-prone. Changing models changes behavior.
5. **Session chaos** — tabs accumulate, ownership is unclear, cleanup is manual.

Vision-capable models can overcome some of these, but the existing browser tooling (raw CDP MCP, Puppeteer wrappers) is too low-level for either class of model.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Hermes Agent                   │
│         (DeepSeek v4, GPT-5.5, Claude, etc.)     │
└─────────────────────┬───────────────────────────┘
                      │ MCP (stdio)
┌─────────────────────▼───────────────────────────┐
│                 Browzer MCP Server               │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │          Semantic Browser Layer           │   │
│  │  ┌─────────┐  ┌────────┐  ┌──────────┐   │   │
│  │  │  State   │  │ Action │  │ Extract  │   │   │
│  │  │  Engine  │  │ Engine │  │  Engine  │   │   │
│  │  └────┬─────┘  └───┬────┘  └────┬─────┘   │   │
│  │       │            │            │          │   │
│  │  ┌────▼────────────▼────────────▼─────┐   │   │
│  │  │        Page Model (Indexed)        │   │   │
│  │  └────────────────┬───────────────────┘   │   │
│  └───────────────────┼───────────────────────┘   │
│                      │                            │
│  ┌───────────────────▼───────────────────────┐   │
│  │         Vision Mediation Layer             │   │
│  │  ┌──────────────┐  ┌───────────────────┐  │   │
│  │  │ Screenshot   │  │ Vision LLM Client │  │   │
│  │  │ Capture      │  │ (configurable)    │  │   │
│  │  └──────────────┘  └───────────────────┘  │   │
│  └───────────────────┬───────────────────────┘   │
│                      │                            │
│  ┌───────────────────▼───────────────────────┐   │
│  │          Transport Layer                   │   │
│  │  ┌──────────────────────────────────────┐ │   │
│  │  │  Codex Chrome Extension Bridge       │ │   │
│  │  │  (ws://127.0.0.1:9224 JSON-RPC)     │ │   │
│  │  └──────────────────────────────────────┘ │   │
│  └───────────────────┬───────────────────────┘   │
└──────────────────────┼───────────────────────────┘
                       │ Native Messaging
┌──────────────────────▼──────────────────────────┐
│           Codex Chrome Extension                 │
│      (hehggadaopoacecdllhhajmbjkdcmajg)          │
└──────────────────────┬──────────────────────────┘
                       │ CDP
┌──────────────────────▼──────────────────────────┐
│               Chrome Browser                     │
│          (existing user profile)                 │
└─────────────────────────────────────────────────┘
```

### Layer Responsibilities

**Semantic Browser Layer**
- Converts raw DOM/accessibility tree into compact indexed page state.
- Assigns stable refs (`@e1`, `@e2`) to interactive elements.
- Exposes high-level tools: `browser_state`, `browser_click_ref`, `browser_fill_ref`, `browser_extract`, `browser_act`.
- Handles tab lifecycle: reuse, tracking, cleanup.

**Vision Mediation Layer**
- Captures screenshots via CDP.
- Routes screenshots + queries to a configurable vision LLM.
- Returns structured observations: element descriptions, text regions, layout descriptions, action recommendations.
- Two operation modes:
  - **Mediated mode** (for non-vision models): vision LLM enriches text state. Model acts through refs.
  - **Direct mode** (for vision-capable models): vision LLM produces coordinate actions directly.

**Transport Layer**
- Talks to the Codex Chrome extension bridge over WebSocket (port 9224).
- Manages WebSocket lifecycle, session ownership, CDP command execution.
- Maintains tab ownership tracking (`claimUserTab`, `attach`).

### Page State Model

Browzer transforms the raw page into this format for LLMs:

```
<page_stats>
12 links, 7 interactive, 1 iframe, 98 total elements
</page_stats>

Current tab: abcd
Available tabs:
  abcd: https://gemini.google.com — Google Gemini

<scroll_info>
0.0 pages above, 1.2 pages below — scroll to see more
</scroll_info>

Interactive elements:
@e1 [textbox] "Ask Gemini" placeholder="Ask Gemini" enabled
@e2 [button] "Send message" disabled
@e3 [button] "New chat" enabled

Visible text:
Gemini
Conversation with Gemini
...
```

The JSON equivalent is also available for programmatic consumers.

Elements are indexed with `@eN` refs. Models interact through refs, never raw selectors.

---

## Browsing Modes

### Mode 1: Vision-Enriched Text Path

For non-vision models (DeepSeek v4, etc.).

1. Model calls `browser_state(tab_id)`.
2. Browzer returns indexed element list + page text.
3. Optionally, model calls `browser_observe(instruction="describe the main content area")`.
4. Browzer captures screenshot, sends to vision LLM, returns text description.
5. Model decides actions via refs: `browser_click_ref(ref="@e3")`, `browser_fill_ref(ref="@e1", text="hi")`.
6. Results include state deltas so model doesn't need to re-scan.

### Mode 2: Vision-First Path

For vision-capable models (GPT-5.5, Gemini, Claude).

1. Model calls `browser_start(url, mode="vision")`.
2. Browzer returns initial screenshot + indexed DOM as context.
3. Model calls `browser_act(instruction="type hi and send it")`.
4. Browzer routes screenshot + instruction to vision LLM.
5. Vision LLM returns: "Type into the textbox at bottom of page. Click the Send button."
6. Browzer translates to refs/coordinates internally and executes.
7. Returns screenshot of result + state delta.

### Mode Selection

- If Browzer is configured with a vision LLM AND the Hermes main model is non-vision → **Mode 1** (enriched text).
- If both Browzer vision LLM and Hermes main model are vision-capable → user chooses mode via config flag `BROWZER_DRIVE_MODE=vision|mediated`.
- If no vision LLM configured → fallback to basic text-only mode with best-effort DOM analysis.

---

## Vision LLM Configuration

Browzer does not hardcode a vision provider. User configures via environment variables or a config file:

```bash
# Required
BROWZER_VISION_BASE_URL=http://127.0.0.1:2455/v1
BROWZER_VISION_MODEL=gpt-5.5
BROWZER_VISION_API_KEY=sk-xxx

# Optional
BROWZER_VISION_MAX_TOKENS=1024
BROWZER_VISION_TEMPERATURE=0
BROWZER_VISION_TIMEOUT=30
BROWZER_DRIVE_MODE=mediated    # or "vision"
```

Any OpenAI-compatible vision endpoint works. Tested targets: codex-lb, OpenAI, Anthropic, Google Gemini.

---

## Tool API

### v0.1 Tools

| Tool | Description | Output |
|------|-------------|--------|
| `browser_start(url, mode?, reuse?)` | Open or reuse a tab. Returns tab_id + initial state. | `{tab_id, reused, state}` |
| `browser_state(tab_id)` | Get indexed interactive elements + page text + stats. | `{page, stats, scroll, elements[], tabs[]}` |
| `browser_observe(tab_id, instruction)` | Send screenshot + instruction to vision LLM. Returns text observation. | `{ok, observations[], state_snapshot?}` |
| `browser_click_ref(tab_id, ref)` | Click element by ref (e.g., `@e3`). | `{ok, clicked, state_delta}` |
| `browser_fill_ref(tab_id, ref, text, submit?)` | Fill input by ref. Optionally submit. | `{ok, filled, state_delta}` |
| `browser_act(tab_id, instruction)` | Natural-language action. Routes to appropriate mode (vision or heuristic). | `{ok, steps[], state_delta}` |
| `browser_extract(tab_id, query, schema?)` | Extract structured data from page. Uses markdown + LLM extraction. | `{data, source_refs}` |
| `browser_scroll(tab_id, direction, pages)` | Scroll page or specific element. | `{ok, scroll_info}` |
| `browser_switch_tab(tab_id)` | Switch to a different tab. | `{ok, state}` |
| `browser_close_tab(tab_id)` | Close a tab (only Browzer-owned). | `{ok, closed}` |
| `browser_cleanup(keep_tab_id?, dry_run?)` | Close unused Browzer-controlled tabs. Defaults to dry-run. | `{dry_run, candidates[], closed[]}` |

### Alpha / v0.2 Tools (future)

| Tool | Description |
|------|-------------|
| `browser_take_screenshot(tab_id)` | Return screenshot as base64 (for vision models). |
| `browser_click_coordinate(tab_id, x, y)` | Direct coordinate click (vision-first mode). |
| `browser_find_element(tab_id, description)` | LLM-assisted element finding. Returns ref. |
| `browser_wait_for(tab_id, condition)` | Wait for text, element, or navigation. |
| `browser_navigate(tab_id, url)` | Navigate existing tab to new URL. |
| `browser_new_tab(url)` | Force a fresh tab (bypasses reuse). |

---

## Tab Lifecycle

Browzer owns its tabs. When it opens or claims a tab, that tab is tracked in an internal `TabManager`.

Rules:
1. **Reuse first** — `browser_start` calls `browser_get_or_open_tab` internally. If a matching tab exists (by URL domain, title, or explicit tab_id), reuse it.
2. **Claim on first use** — `claimUserTab` + `attach` on first interaction.
3. **Track ownership** — internal set of `created_tabs` and `owned_tabs`.
4. **Cleanup is explicit** — Browzer never closes tabs without user/agent direction. `browser_cleanup` defaults to `dry_run=true`. Only tabs flagged as `hermes-created` or `owned-blank` are eligible.
5. **User tabs are safe** — tabs not owned/created by Browzer cannot be closed through Browzer tools.

---

## Comparison with Existing Solutions

| | Browserbase | browser-use | Playwright MCP | Browzer |
|---|---|---|---|---|
| **Browser** | Cloud Chrome | Local/CDP Chrome | Playwright | User's Chrome via Codex bridge |
| **Cookies/Profile** | Fresh/stealth | Fresh profile | Fresh context | **User's existing profile** |
| **Vision model** | Stagehand (built-in) | Optional (`use_vision`) | None (text/DOM) | **Configurable bring-your-own** |
| **Non-vision path** | Observe/act/extract | Indexed elements | Accessibility snapshots | **Vision-enriched + indexed** |
| **MCP server** | Yes (hosted) | Via wrapper | Yes | **Yes (self-hosted)** |
| **Tab reuse** | Session mgmt | Basic | No | **Reuse-first policy** |

Key differentiator: **bring your own browser and bring your own vision model**. No cloud dependency, no fresh sessions, no vendor lock.

---

## v0.1 Scope

### Must Have
- [ ] MCP server entrypoint (`browzer serve` or `python -m browzer`)
- [ ] Codex Chrome bridge transport layer
- [ ] `browser_start` with tab reuse
- [ ] `browser_state` with indexed interactive elements
- [ ] `browser_click_ref`
- [ ] `browser_fill_ref`
- [ ] `browser_observe` (vision-enriched text path)
- [ ] Vision LLM client (configurable OpenAI-compatible endpoint)
- [ ] Tab lifecycle: creation, ownership, reuse, cleanup
- [ ] Cleanup tool with dry-run default

### Nice to Have
- [ ] `browser_act` (heuristic + vision routing)
- [ ] `browser_extract` (markdown extraction)
- [ ] Vision-first direct mode (coordinate actions)
- [ ] Screenshot capture tool

### Out of Scope (v0.2+)
- [ ] Playwright / standard CDP backends
- [ ] Browserbase / remote Chrome support
- [ ] Multi-tab orchestration (parallel tabs)
- [ ] Session recording / replay
- [ ] Plugin system
- [ ] Hosted/SaaS version

---

## Project Structure

```
browzer/
├── README.md
├── PRD.md
├── pyproject.toml
├── src/
│   └── browzer/
│       ├── __init__.py
│       ├── server.py           # FastMCP server, tool registration
│       ├── bridge.py           # Codex Chrome bridge client (WebSocket JSON-RPC)
│       ├── transport.py        # Low-level: connect, rpc, cdp, tab ops
│       ├── state_engine.py     # DOM → indexed page state
│       ├── action_engine.py    # Click, fill, scroll by ref
│       ├── extract_engine.py   # Markdown extraction, structured output
│       ├── vision/
│       │   ├── __init__.py
│       │   ├── client.py       # OpenAI-compatible vision API client
│       │   ├── observe.py      # Screenshot + vision LLM → observations
│       │   └── act.py          # Vision-first action routing
│       ├── tab_manager.py      # Tab lifecycle: create, claim, attach, reuse, cleanup
│       ├── element_store.py    # Ref ↔ backendNodeId mapping per tab
│       └── config.py           # Env/config loading
├── tests/
└── examples/
    └── hermes-config.yaml      # Example Hermes MCP config snippet
```

---

## Dependencies

```
# Core
websockets>=12
mcp>=1.0

# Vision client
httpx>=0.27
openai>=1.0        # For OpenAI-compatible vision endpoint

# Optional
Pillow>=10         # Screenshot processing
beautifulsoup4     # Markdown extraction (future)
```

---

## Example Usage

### Hermes Config

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

### Environment

```bash
# ~/.hermes/.env or shell
export CODEX_CHROME_BRIDGE_URL=ws://127.0.0.1:9224
export BROWZER_VISION_BASE_URL=http://127.0.0.1:2455/v1
export BROWZER_VISION_MODEL=gpt-5.5
export BROWZER_VISION_API_KEY=sk-xxx
export BROWZER_DRIVE_MODE=mediated
```

### Session Example (Text Path)

```
User: Open Gemini and say hi

Hermes → browser_start(url="https://gemini.google.com/app")
Browzer → {tab_id: 1292176900, reused: false, state: {...}}

Hermes → browser_state(tab_id=1292176900)
Browzer → {
  elements: [
    {ref: "@e1", role: "textbox", name: "Ask Gemini", action: "type"},
    {ref: "@e2", role: "button", name: "Send message", action: "click"}
  ],
  ...
}

Hermes → browser_fill_ref(tab_id=1292176900, ref="@e1", text="hi", submit=true)
Browzer → {ok: true, filled: "@e1", submitted: true, state_delta: {new_text: "Gemini said..."}}

Hermes → browser_cleanup(keep_tab_id=1292176900)
Browzer → {dry_run: true, candidates: [], closed: []}
```

### Session Example (Vision Path)

```
User: Log into example.com with user@test.com / password123

Hermes → browser_start(url="https://example.com/login", mode="vision")
Browzer → {tab_id: ..., screenshot: <base64>, elements: [...]}

Hermes → browser_act(tab_id=..., instruction="log in with user@test.com / password123")
Browzer → captures screenshot → sends to vision LLM →
  vision LLM: "Email field at top-left. Password field below. Submit button bottom."
  Browzer executes: fill "@e4" with user@test.com, fill "@e5" with password123, click "@e7"
Browzer → {ok: true, steps: [...], screenshot: <result>}
```

---

## Open Questions

1. **Vision LLM prompt format** — should Browzer use a standardized system prompt for the vision LLM, or let the user configure it? Current thinking: sensible default with `BROWZER_VISION_SYSTEM_PROMPT` override.

2. **Screenshot resolution** — what dimensions to capture at? Full page or viewport? Current thinking: viewport at Chrome's current size, `BROWZER_SCREENSHOT_WIDTH` / `BROWZER_SCREENSHOT_QUALITY` tunables.

3. **WebSocket reconnection** — the Codex bridge session is per-WebSocket-connection. If the WebSocket drops, all tab attachments are lost. Should Browzer auto-reconnect and re-claim tabs? Current thinking: auto-reconnect with exponential backoff, re-claim+re-attach owned tabs.

4. **Concurrent sessions** — if two Hermes sessions connect to Browzer, can they share tabs? Should each MCP connection be isolated? Current thinking: one MCP connection = one session, tabs are not shared between MCP connections. Each Hermes session gets its own Browzer session.

5. **Element staleness** — after a DOM mutation, refs may point to removed nodes. Should Browzer auto-refresh state after each action? Current thinking: yes, `browser_state` should be re-fetched after each action, and actions return a `state_delta` for efficiency.

---

## Success Metrics

- **Reliability**: >90% of basic web interactions (click, type, submit) succeed on first attempt on major sites (Gemini, GitHub, Gmail).
- **Non-vision parity**: DeepSeek v4 completes a simple web task (open site, read response) in <= 3 tool calls with Browzer vs. manual scripting with raw bridge.
- **Vision mode quality**: Vision-first mode correctly identifies and clicks elements on canvas-heavy or visually-complex pages that DOM-only approaches fail on.
- **No tab leaks**: After 20 consecutive sessions, zero unused Browzer tabs remain open in Chrome.
- **Install time**: Sub-5-minute setup from git clone to first working `browser_state` call.
