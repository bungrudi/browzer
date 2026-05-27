# Browzer

Semantic, vision-augmented MCP browser server for AI agents.

Browzer gives LLMs a clean, indexed interface to Chrome through the
Codex Chrome extension bridge. Non-vision models get vision-enriched
text snapshots; vision models can drive the browser directly.

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/bungrudi/browzer
cd browzer
uv venv
uv pip install -e .

# 2. Add to Hermes config (~/.hermes/config.yaml)
mcp_servers:
  browzer:
    command: /path/to/browzer/.venv/bin/python
    args:
      - -m
      - browzer
    timeout: 120

# 3. (Optional) Configure vision LLM
export BROWZER_VISION_BASE_URL=http://127.0.0.1:2455/v1
export BROWZER_VISION_MODEL=gemini-2.5-flash-lite
export BROWZER_VISION_API_KEY=your-key
```

## Prerequisites

- Chrome with the [Codex Chrome Extension](https://chromewebstore.google.com/detail/hehggadaopoacecdllhhajmbjkdcmajg) installed
- Codex Native Host Bridge running on port 9224
- Python 3.11+

## How It Works

```
Hermes Agent (DeepSeek v4, GPT-5.5, ...)
        │ MCP (stdio)
        ▼
  Browzer MCP Server
   ├── State Engine     → DOM → indexed elements (@e1, @e2)
   ├── Action Engine    → click/fill/scroll by ref
   ├── Vision Layer     → screenshot + vision LLM → text observations
   └── Transport        → WebSocket → Codex Chrome Extension → CDP
```

### Two Browsing Modes

**Mediated (for non-vision models like DeepSeek v4):**
```
browser_start(url) → browser_state(tab_id) → get indexed elements
browser_observe(tab_id, "describe the page") → vision LLM enriches text
browser_click_ref(tab_id, "@e3") → click by stable ref
```

**Vision-first (for vision-capable models):**
```
browser_start(url, mode="vision") → get screenshot + DOM
browser_observe(tab_id, "find and click the login button")
```

## Tools

| Tool | Description |
|------|-------------|
| `browser_start(url, mode, reuse)` | Open or reuse a tab |
| `browser_state(tab_id, format)` | Get indexed elements + page text |
| `browser_observe(tab_id, instruction)` | Screenshot → vision LLM → description |
| `browser_click_ref(tab_id, ref)` | Click element by ref (@e3) |
| `browser_fill_ref(tab_id, ref, text, submit)` | Fill input by ref |
| `browser_scroll(tab_id, direction, pages)` | Scroll page |
| `browser_switch_tab(tab_id)` | Switch active tab |
| `browser_close_tab(tab_id)` | Close owned tab |
| `browser_cleanup(keep_tab_id, dry_run)` | Clean up unused tabs |
| `browser_eval(tab_id, expression)` | Evaluate JavaScript |
| `browser_press_key(tab_id, key)` | Press keyboard key |

## Configuration

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEX_CHROME_BRIDGE_URL` | `ws://127.0.0.1:9224` | Bridge WebSocket URL |
| `BROWZER_VISION_BASE_URL` | `http://127.0.0.1:2455/v1` | Vision LLM endpoint |
| `BROWZER_VISION_MODEL` | `gemini-2.5-flash-lite` | Vision model name |
| `BROWZER_VISION_API_KEY` | — | API key for vision endpoint |
| `BROWZER_DRIVE_MODE` | `mediated` | `mediated` or `vision` |
| `BROWZER_SCREENSHOT_QUALITY` | `80` | Screenshot JPEG quality |
| `BROWZER_SESSION_ID` | `browzer` | Bridge session identifier |

## Design

- **Reuse-first tabs**: Finds existing tabs before creating new ones
- **Safe cleanup**: Dry-run by default, never closes user tabs
- **Stable refs**: Elements get `@e1, @e2` refs — no CSS selector guessing
- **SPA-friendly**: Uses native input setters + React/Angular event dispatch
- **Bring your own vision model**: Any OpenAI-compatible endpoint works

## Architecture

```
browzer/
├── src/browzer/
│   ├── server.py          # FastMCP server, tool registration
│   ├── bridge.py          # Codex Chrome bridge high-level API
│   ├── transport.py       # WebSocket JSON-RPC client
│   ├── tab_manager.py     # Tab lifecycle: create, claim, reuse, cleanup
│   ├── element_store.py   # Ref ↔ backendNodeId mapping
│   ├── state_engine.py    # DOM → indexed page state
│   ├── action_engine.py   # Click, fill, scroll by ref
│   ├── config.py          # Env-based configuration
│   └── vision/
│       ├── client.py      # OpenAI-compatible vision API client
│       └── observe.py     # Screenshot + vision observation
├── docs/
│   └── plan-v0.1.md       # Implementation plan
└── examples/
    └── hermes-config.yaml # Example Hermes MCP config
```

## vs Alternatives

| | Browserbase | Playwright MCP | Browzer |
|---|---|---|---|
| Browser | Cloud | Fresh context | **Your Chrome** |
| Profile | Fresh | Fresh | **Your cookies/logins** |
| Vision | Built-in | None | **Bring your own** |
| Non-vision | Indexed | A11y snapshots | **Vision-enriched + indexed** |
| Self-hosted | No | Yes | **Yes** |
| Tab reuse | Basic | No | **Reuse-first** |
