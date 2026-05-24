# adb-mcp

> Advanced Android Debug Bridge MCP server — optimised for **small LLMs** (gpt-oss-20b, qwen3vl).
> 15 semantic tools, OCR + Set-of-Mark dual-path screen understanding, no coordinate hallucinations.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/HarounAbdelsamad/adb-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/HarounAbdelsamad/adb-mcp/actions)
[![MCP](https://img.shields.io/badge/MCP-server-purple)](https://modelcontextprotocol.io)
[![uv compatible](https://img.shields.io/badge/uv-compatible-brightgreen)](https://github.com/astral-sh/uv)

<!-- Once a demo gif is recorded, drop it into assets/demo.gif and uncomment:
![demo](assets/demo.gif)
-->

---

## Quick Start (30 seconds)

```bash
# 1. Install
uv tool install adb-mcp        # or: pip install adb-mcp

# 2. Plug in a phone with USB debugging enabled, confirm it shows up
adb devices

# 3. Wire it into any MCP client (the JSON below is the same across
#    Claude Desktop, Cursor, Cline, Antigravity, OpenCode, LM Studio,
#    mcphost, …)
{
  "mcpServers": {
    "adb": { "command": "adb-mcp" }
  }
}
```

Now ask your agent: *"Open Wi-Fi settings on my Android device and turn Wi-Fi
off."* The model uses `open_settings`, `get_screen`, then `tap` on the
toggle — no coordinates touched.

---

## Why this exists

Most ADB MCP servers expose raw coordinates and 20–50 loosely-named tools.
Small models (sub-20B) hallucinate pixel positions and fail tool selection
once the surface exceeds ~19 tools. This server is different:

- **Semantic-first actions** — tap by `text`, `resource_id`, or `content_desc`;
  coordinates are the last resort.
- **Dual screen paths** — `get_screen` returns an accessibility tree + OCR
  JSON for text-only models *and* a Set-of-Mark numbered screenshot for
  vision models, sharing one snapshot and one ID space.
- **Exactly 15 tools** — tuned to stay well under the documented accuracy
  cliff for 20B-class models.
- **Structured errors with hints** — every tool failure tells the model
  exactly what to try next, so it self-corrects instead of giving up.
- **Settings/onboarding focused** — `open_settings` deep-links into 25
  Android settings panels; `grant_permission` handles runtime permission
  flows.

### Comparison with other ADB MCPs

| Server | Tools | Lang | Semantic selectors | OCR path | SoM vision path | Structured errors |
|---|---|---|:---:|:---:|:---:|:---:|
| **adb-mcp** | 15 | Python | ✅ | ✅ | ✅ | ✅ |
| [minhalvp/android-mcp-server](https://github.com/minhalvp/android-mcp-server) | 5 | Python | ❌ | ❌ | ❌ | ❌ |
| [nim444/mcp-android-server-python](https://github.com/nim444/mcp-android-server-python) | 26 | Python | partial | ❌ | ❌ | ❌ |
| [TiagoDanin/Android-Debug-Bridge-MCP](https://github.com/TiagoDanin/Android-Debug-Bridge-MCP) | ~8 | TS | ❌ | ❌ | ❌ | ❌ |

---

## Installation

### With uv (recommended)

```bash
# As a global tool (best for daily use)
uv tool install adb-mcp
adb-mcp --help

# Or one-shot without persistent install
uvx adb-mcp
```

### With pip

```bash
pip install adb-mcp
adb-mcp --help
```

### From source (development)

```bash
git clone https://github.com/HarounAbdelsamad/adb-mcp.git
cd adb-mcp

# uv path
uv sync
uv run adb-mcp --help

# pip path
pip install -e ".[dev]"
adb-mcp --help
```

> The first `get_screen` call with `ocr_enabled: true` downloads the PaddleOCR
> model weights (~150 MB) automatically.

---

## Recommended models

Tested with Ollama-hosted models, BFCL-V4 tool-calling benchmarks, and real
`get_screen` payloads (UI tree JSON typically 4–8 KB).

### 16 GB VRAM (e.g. RTX 5080, 4080) — primary target

| Model | Pull command | VRAM | Why |
|---|---|---|---|
| **`qwen3:14b`** ⭐ | `ollama pull qwen3:14b` | ~8 GB | Best open-source tool calling at this size, ~72% BFCL-V4. Plenty of headroom for our large `get_screen` payloads. |
| `gpt-oss:20b` | `ollama pull gpt-oss:20b` | ~13 GB | Strong reasoning but tight on VRAM — workable, no headroom for huge contexts. |
| `qwen2.5vl:7b` | `ollama pull qwen2.5vl:7b` | ~6 GB | **Vision path** — pair with `mode="vision"` for SoM-based agents. Best OCR currently in Ollama. |

### 8–12 GB VRAM (RTX 3060 / 4060 / mid-laptops)

| Model | Pull command | VRAM |
|---|---|---|
| `qwen2.5:7b-instruct` | `ollama pull qwen2.5:7b-instruct` | ~5 GB |
| `llama3.1:8b` | `ollama pull llama3.1:8b` | ~5 GB |
| `qwen2.5vl:7b` (vision) | `ollama pull qwen2.5vl:7b` | ~6 GB |

### 24 GB+ VRAM (RTX 3090 / 4090 / A5000)

| Model | Pull command | VRAM |
|---|---|---|
| `qwen3:32b` | `ollama pull qwen3:32b` | ~19 GB |
| `qwen2.5:32b-instruct` | `ollama pull qwen2.5:32b-instruct` | ~19 GB |

### Cloud / no GPU

- **Anthropic Claude** (Sonnet / Opus) — strongest tool calling overall, used by Claude Desktop, Cursor, Cline, OpenCode.
- **OpenAI GPT-4o / GPT-4.1** — top-tier tool calling, works with any OpenAI-compatible MCP host.
- **Ollama Cloud `gpt-oss:120b`** — open-weights frontier model via hosted Ollama.
- **Google Gemini** — via Antigravity or OpenAI-compatible bridges.

> 💡 If you're unsure: **start with `qwen3:14b`** on 16 GB VRAM. It's the best
> balance of tool-calling accuracy, context headroom, and inference speed for
> this server's workload.

---

## Configuration

```bash
cp config.example.yaml config.yaml
```

| Key | Default | Description |
|---|---|---|
| `adb_path` | `adb` | Path to the adb binary |
| `default_device` | `null` | Device serial for multi-device setups |
| `ocr_enabled` | `true` | Enable server-side OCR for text-only models |
| `ocr_engine` | `paddle` | `paddle`, `tesseract`, or `none` |
| `screenshot_max_dim` | `1280` | Downscale screenshots to this max dimension |
| `som_default_enabled` | `true` | Overlay numbered badges on vision screenshots |
| `destructive_ops_enabled` | `false` | Allow `grant_permission` revoke action |

Override any key with `ADB_MCP_` env vars, e.g. `ADB_MCP_LOG_LEVEL=DEBUG`.

---

## The 15 tools

| Tool | Description |
|---|---|
| `list_devices` | List connected ADB devices |
| `device_info` | Screen size, DPI, battery, Android version |
| **`get_screen`** | **UI tree + OCR + SoM screenshot in one call** |
| `wait_for` | Block until selector appears/disappears |
| `tap` | Tap by selector (id/text/resource_id/content_desc) or coords |
| `swipe` | Swipe by direction, selector pair, or coordinates |
| `type_text` | Type into focused field or a selector target |
| `press_key` | back, home, enter, delete, recent, volume, … |
| `launch_app` | Launch by package, package+activity, or deep-link URI |
| `list_packages` | List installed packages with optional name filter |
| `app_info` | Version, permissions, main activity, foreground status |
| **`open_settings`** | **Deep-link to wifi, bluetooth, app_details, accessibility, …** |
| `grant_permission` | Grant (or revoke) a runtime permission |
| `get_logcat` | Structured logcat with tag + priority filter |
| `dumpsys_query` | Query window, activity, battery, power, wifi, and more |

### `get_screen` — dual-path explained

```text
mode="text"    →  tree (JSON) + OCR spans (JSON)        ← gpt-oss-20b (no vision)
mode="vision"  →  tree (JSON) + SoM-annotated PNG       ← qwen3vl, qwen2.5vl
mode="both"    →  all three                             ← default
```

The integer `id` in every tree node matches the badge number in the image
and is accepted directly by `tap`:

```python
# After get_screen, tap element 7 by its SoM id — no coordinates needed:
tap(selector={"id": 7})
```

### Selector keys

| Key | Score | Behaviour |
|---|---|---|
| `resource_id` | +10 | Highest — Android stable widget id |
| `text` (exact) | +6 | Exact text match |
| `content_desc` | +4 | Accessibility description |
| `class` | +3 | Widget class substring |
| `text_contains` | +2 | Substring match |
| `id` (SoM) | O(1) | Direct lookup against last snapshot |
| `index` | — | Disambiguate Nth tied match |

Ambiguous selectors return a structured error with the top 3 candidates and
their ids so the model can immediately retry with `index` or a narrower key.

### `open_settings` panels

`home` `wifi` `bluetooth` `data_usage` `mobile_data` `airplane_mode` `network`
`display` `sound` `notifications` `apps` `app_details` `default_apps`
`accessibility` `language` `date_time` `location` `security` `privacy`
`battery` `storage` `developer` `accounts` `about` `nfc` `hotspot`

Pass `package=` alongside `app_details`.

---

## Example agent flow

User prompt: *"Turn off Wi-Fi."*

```
agent: list_devices()
  → {"ok": true, "devices": [{"serial":"R3CN30...", "model":"Pixel 8", ...}]}

agent: open_settings(panel="wifi")
  → {"ok": true, "panel":"wifi", "intent_used":"android.settings.WIFI_SETTINGS"}

agent: get_screen(mode="text")
  → {"ok": true, "snapshot_id":"7c40...",
     "tree": [
       {"id":3,"text":"Wi-Fi","resource_id":"com.android.settings:id/switch_widget",
        "clickable":true,"bounds":{...}, ...},
       {"id":4,"text":"Use Wi-Fi","clickable":true, ...},
       ...
     ],
     "ocr": [...]}

agent: tap(selector={"id": 3})
  → {"ok": true, "resolved":{"strategy":"id","node":{"id":3,...}}, "x":960, "y":280}

agent: get_screen(mode="text")
  → ... toggle is now off, screen reflects it ...
```

Note: the model picked the toggle by its SoM `id`, never reasoning about
pixel positions. The same flow works on a 1080×2400 Pixel as on a 720×1600
Samsung — selectors are resolution-independent.

---

## Compatible clients

`adb-mcp` speaks the standard Model Context Protocol over stdio, so it works
with every MCP-capable host. Ready-to-use snippets live in
[examples/](examples/). The `mcpServers` JSON shape is shared across most
clients — usually you just paste the snippet into the right config file.

### Claude Desktop

File: `claude_desktop_config.json` ([example](examples/claude_desktop_config.json))

```json
{
  "mcpServers": {
    "adb": {
      "command": "adb-mcp",
      "env": { "ADB_MCP_CONFIG": "C:\\path\\to\\config.yaml" }
    }
  }
}
```

### Cursor

File: `~/.cursor/mcp.json` (or project-local `.cursor/mcp.json`) ([example](examples/cursor.mcp.json))

```json
{
  "mcpServers": {
    "adb": { "command": "adb-mcp" }
  }
}
```

### Cline (VS Code)

File: `cline_mcp_settings.json` in the Cline VS Code extension settings ([example](examples/cline_mcp_settings.json))

```json
{
  "mcpServers": {
    "adb": {
      "command": "adb-mcp",
      "disabled": false,
      "autoApprove": ["get_screen", "list_devices", "device_info", "wait_for"]
    }
  }
}
```

### Antigravity

File: `antigravity_mcp_config.json` in your Antigravity workspace ([example](examples/antigravity_mcp_config.json))

```json
{
  "mcpServers": {
    "adb": { "command": "adb-mcp" }
  }
}
```

### OpenCode

File: `opencode.json` in the project root ([example](examples/opencode.json))

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "adb": {
      "type": "local",
      "command": ["adb-mcp"],
      "enabled": true
    }
  }
}
```

### LM Studio

File: `mcp.json` in your LM Studio config directory, or via the in-app
**Program → Install → Edit `mcp.json`** button ([example](examples/lmstudio_mcp.json))

```json
{
  "mcpServers": {
    "adb": { "command": "adb-mcp" }
  }
}
```

LM Studio reuses the standard `mcpServers` shape — once saved, the tools
appear in any chat using a tool-capable local model (Qwen3, Llama 3.1,
Hermes, etc.).

### Ollama (via mcphost)

Ollama itself doesn't speak MCP. Use [mcphost](https://github.com/mark3labs/mcphost)
(or any OpenAI-compatible MCP bridge) to bolt local models onto MCP servers:

```bash
# Install mcphost, then point it at adb-mcp + your favourite Ollama model
mcphost --config examples/mcphost.json --model ollama:qwen3:14b
```

`examples/mcphost.json`:

```json
{
  "mcpServers": {
    "adb": { "command": "adb-mcp" }
  }
}
```

### Anything else

Any stdio-transport MCP client works — point it at the `adb-mcp` binary and
optionally set `ADB_MCP_CONFIG` to your config file. If your favourite client
isn't listed above, add a snippet in [examples/](examples/) and open a PR.

---

## Architecture

```
src/adb_mcp/
├── server.py          FastMCP instance + tool registration
├── config.py          pydantic-settings loader
├── errors.py          ErrorCode enum, @tool_safe decorator
├── device.py          DeviceManager — resolves serials, caches u2 connections
├── ui/
│   ├── tree.py        XML hierarchy → UiNode, filter, prune, ID assignment
│   ├── selector.py    Semantic resolution with scoring + ambiguity errors
│   ├── ocr.py         PaddleOCR + tree-merge (text-only model path)
│   └── som.py         Numbered SoM overlay (vision model path)
├── util/
│   ├── screenshot.py  Capture + downscale
│   └── cache.py       Last-snapshot-per-device store
└── tools/
    ├── screen.py      get_screen, wait_for
    ├── input.py       tap, swipe, type_text, press_key
    ├── apps.py        launch_app, list_packages, app_info
    ├── settings.py    open_settings, grant_permission
    └── diag.py        list_devices, device_info, get_logcat, dumpsys_query
```

---

## Testing

```bash
# Unit tests (no device needed)
uv run pytest tests/ --ignore=tests/integration

# Integration tests (real device required, auto-skip otherwise)
uv run pytest tests/integration/ -v
```

24 unit tests cover tree parsing, selector scoring + ambiguity, SoM rendering.
Integration suite walks Settings → Wi-Fi as an end-to-end check.

---

## Contributing

PRs welcome — please read [CONTRIBUTING.md](CONTRIBUTING.md) first.
The hard constraints (15-tool budget, semantic selectors, structured errors)
are documented there.

---

## License

MIT — see [LICENSE](LICENSE).
