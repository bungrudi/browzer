Build Browzer — an MCP server that gives AI agents a semantic, vision-augmented interface to Chrome through the Codex Chrome extension bridge. Work from ~/Workspace/browzer (repo: https://github.com/bungrudi/browzer). Full PRD at PRD.md.

## v0.1 Must-Have Features (in priority order)

### 1. Vision-enriched text path (highest priority)
Non-vision models (DeepSeek) get vision-augmented text snapshots. Workflow:
- browser_state → indexed elements + page text
- browser_observe → screenshot + vision LLM → text description
- browser_click_ref / browser_fill_ref → actions by ref
Vision LLM is configurable via env: BROWZER_VISION_BASE_URL, BROWZER_VISION_MODEL, BROWZER_VISION_API_KEY.

### 2. Vision-first path
Vision-capable models (GPT-5.5, Gemini) drive browser with screenshots. Workflow:
- browser_start(mode="vision") → screenshot + DOM
- browser_act(instruction) → vision LLM → coordinate/ref actions
- Returns screenshot + state delta.

### 3. Tab lifecycle management
Reuse-first policy, track owned/created tabs, safe cleanup (dry-run default).
Never close user tabs. browser_cleanup only closes hermes-created or owned-blank tabs.

## Architecture (3 layers)
1. Transport: Codex Chrome bridge client (ws://127.0.0.1:9224 JSON-RPC). Tab ownership, CDP execution, WebSocket lifecycle.
2. Semantic Browser: DOM/accessibility → compact indexed page state with refs (@e1, @e2). Action engine (click/fill by ref), extract engine (markdown extraction).
3. Vision Mediation: Screenshot capture + configurable OpenAI-compatible vision LLM client. Mediated mode (vision describes for text models) and direct mode (vision drives actions).

## Project Structure (see PRD.md)

## Tech Stack
- Python 3.11+, FastMCP server
- websockets for Codex bridge
- httpx + openai for vision client
- Venv in ~/Workspace/browzer/.venv

## Existing Code to Build From
- /home/rudi/.hermes/mcp/codex_chrome_mcp.py — current Codex bridge MCP wrapper with tab reuse, bridge client, cdp/eval/snapshot/type/click tools
- Reference implementations: browser-use (indexed elements, selector_map), Playwright MCP (accessibility snapshots), Stagehand (observe/act/extract)

## Constraints
- MCP server for Hermes. Drop-in replacement for codex-chrome MCP.
- Connects to existing Chrome via Codex extension bridge (port 9224).
- One MCP connection = one browser session. Tabs not shared between MCP connections.
- Vision LLM: any OpenAI-compatible endpoint. Test with codex-lb gpt-5.5 at http://127.0.0.1:2455/v1.
- Hermes config entry in ~/.hermes/config.yaml under mcp_servers.browzer.
- Git-cloned repo, venv, standard open-source project layout.

## Open Design Decisions to Resolve First
1. Vision LLM system prompt format — sensible default with override?
2. Screenshot resolution — viewport at current size, tunable via env?
3. WebSocket reconnection — auto-reconnect with exponential backoff, re-claim tabs?
4. Element staleness — auto-refresh state after each action, return state_delta?
5. Concurrent sessions — isolated per MCP connection, confirmed.

## Success Criteria
- DeepSeek v4 completes web task (open Gemini, send message, read response) in ≤ 3 tool calls
- Vision-first mode correctly identifies and clicks elements on canvas-heavy pages
- Zero unused tabs after 20 consecutive sessions
- Sub-5-minute setup from git clone to first browser_state call
