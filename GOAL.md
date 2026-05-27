# Browzer — Hermes Goal Prompt

## How We Work

**Two-model pipeline with Codex delegation:**

| Phase | Model | Actor | Role |
|-------|-------|-------|------|
| Plan | gpt-5.5 | Hermes (you) | Read PRD, decompose into tasks, write implementation plan docs |
| Implement | gpt-5.3-codex | Codex CLI (delegated) | Write code, run tests, iterate until tests pass |
| Review | gpt-5.5 | Hermes (you) | Review diffs, verify spec compliance, final commit |

Codex CLI is invoked via terminal with PTY:

```
terminal(
  command="codex exec -m gpt-5.3-codex --sandbox workspace-write '<task prompt>'",
  workdir="~/Workspace/browzer",
  pty=true,
  background=true,
  notify_on_complete=true
)
```

For smaller tasks use foreground mode; for larger tasks use background with notify_on_complete.

**Workflow per task:**
1. Hermes (gpt-5.5) reads the plan, picks next task, writes a detailed codex prompt
2. Hermes dispatches codex CLI (gpt-5.3-codex) with the prompt
3. Codex outputs a git commit. Hermes reviews the diff, runs full tests, verifies spec
4. If issues: Hermes writes a fix prompt, re-dispatches codex
5. If clean: Hermes marks task done, moves to next

Never hand-code implementation — always delegate to codex CLI for code generation. Hermes' job is planning and review only.

## Project

**Browzer** — an MCP server that gives AI agents a semantic, vision-augmented interface to Chrome through the Codex Chrome extension bridge.

**Repo:** https://github.com/bungrudi/browzer
**Workspace:** ~/Workspace/browzer
**PRD:** ~/Workspace/browzer/PRD.md

## Architecture (3 layers)

1. **Transport layer** — Codex Chrome bridge client (ws://127.0.0.1:9224 JSON-RPC). Tab ownership, CDP execution, WebSocket lifecycle.
2. **Semantic browser layer** — DOM/accessibility → compact indexed page state with refs (@e1, @e2). Action engine (click/fill by ref), extract engine.
3. **Vision mediation layer** — Screenshot capture + configurable OpenAI-compatible vision LLM client. Two modes: mediated (vision describes for text models) and direct (vision drives actions).

## v0.1 Must-Have Features (priority order)

### Feature 1: Vision-enriched text path
Non-vision models (DeepSeek) get vision-augmented text snapshots.
- `browser_state` → indexed elements + page text
- `browser_observe` → screenshot + vision LLM → text description
- `browser_click_ref` / `browser_fill_ref` → actions by ref
- Vision LLM configurable via env: BROWZER_VISION_BASE_URL, BROWZER_VISION_MODEL, BROWZER_VISION_API_KEY

### Feature 2: Vision-first path
Vision-capable models (GPT-5.5, Gemini) drive browser with screenshots.
- `browser_start(mode="vision")` → screenshot + DOM
- `browser_act(instruction)` → vision LLM → coordinate/ref actions

### Feature 3: Tab lifecycle management
Reuse-first policy, track owned/created tabs, safe cleanup (dry-run default). Never close user tabs.

## Implementation Plan (to be created by Hermes)

1. Read the PRD fully
2. Create a detailed implementation plan at ~/Workspace/browzer/docs/plan-v0.1.md
3. Decompose into bite-sized tasks, each completable by codex CLI in one shot
4. Execute tasks via codex CLI delegation
5. After each task: review, test, commit/push

## Tech Stack
- Python 3.11+, FastMCP (`mcp` package)
- `websockets` for Codex bridge
- `httpx` + `openai` for vision client
- Venv: ~/Workspace/browzer/.venv (create with `uv venv` if not present)

## Constraints
- MCP server for Hermes. Drop-in replacement for codex-chrome MCP.
- Connects to existing Chrome via Codex extension bridge (port 9224).
- One MCP connection = one browser session.
- Vision LLM: any OpenAI-compatible endpoint. Test with codex-lb gpt-5.5 at http://127.0.0.1:2455/v1.
- Hermes config entry in ~/.hermes/config.yaml under mcp_servers.browzer.

## Open Design Decisions
1. Vision LLM system prompt format — sensible default with BROWZER_VISION_SYSTEM_PROMPT override?
2. Screenshot resolution — viewport at current size, BROWZER_SCREENSHOT_WIDTH/QUALITY tunables?
3. WebSocket reconnection — auto-reconnect with exponential backoff, re-claim tabs?
4. Element staleness — auto-refresh state after each action, return state_delta?
5. Concurrent sessions — isolated per MCP connection (confirmed)

## Success Criteria
- DeepSeek v4 completes web task (open Gemini, send message, read response) in ≤ 3 tool calls
- Vision-first mode correctly identifies and clicks elements on canvas-heavy pages
- Zero unused tabs after 20 consecutive sessions
- Sub-5-minute setup from git clone to first browser_state call

## First Steps (do these now)
1. Create ~/Workspace/browzer/.venv with `uv venv` if not present
2. Install deps: `uv pip install websockets mcp httpx openai`
3. Load the chrome-cdp skill for Codex bridge protocol reference
4. Create docs/plan-v0.1.md with detailed implementation plan
5. Begin delegating tasks to codex CLI one at a time
