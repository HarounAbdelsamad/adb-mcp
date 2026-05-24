# Contributing to adb-mcp

Thanks for considering a contribution! adb-mcp is a small, focused project — the
fastest way to get a PR merged is to keep changes scoped and align with the
existing design (15-tool budget, semantic selectors over coordinates,
structured error payloads).

## Quick setup

```bash
git clone https://github.com/HarounAbdelsamad/adb-mcp.git
cd adb-mcp

# With uv (recommended)
uv sync
uv run pytest tests/ --ignore=tests/integration

# Or with pip
pip install -e ".[dev]"
pytest tests/ --ignore=tests/integration
```

## Running the integration tests

The `tests/integration/` suite needs a real Android device attached via ADB:

```bash
# Confirm device is visible
adb devices

# Run integration tests
uv run pytest tests/integration -v
```

Tests auto-skip when no device is present, so CI on GitHub Actions only runs
the unit suite.

## Code style

- Format and lint with `ruff`:
  ```bash
  uv run ruff check src tests
  uv run ruff format src tests
  ```
- Target Python 3.10+ syntax.
- Type hints on every public function. `from __future__ import annotations`
  at the top of every module.
- No emoji in code or commit messages unless explicitly part of UI strings.

## Design constraints to keep in mind

These are **hard limits**, not preferences:

1. **15 tools maximum.** Adding a 16th means removing one. The tool count
   sits below the documented small-model accuracy cliff (~19 tools). If you
   need new functionality, prefer extending an existing tool (e.g. a new
   `open_settings` panel) or composing two tools at the agent layer.
2. **Semantic selectors first, coordinates last.** Any new action tool must
   accept a `selector` dict (using `resource_id`, `text`, `content_desc`,
   `class`, or SoM `id`) before falling back to `x,y`.
3. **Tools return structured JSON, never raise.** Wrap every tool with
   `@tool_safe`. Errors must have `error_code`, `message`, and (when
   useful) `hint` so the model can self-correct.
4. **Output schema is part of the API.** If you change a tool's return
   shape, bump the version and document it in the CHANGELOG.

## Submitting a PR

1. **Open an issue first** if the change is more than ~20 lines or touches
   the tool surface. We agree on shape there before code is written.
2. Branch from `main`: `git switch -c feat/short-description`.
3. Add tests. Unit tests live next to existing ones in `tests/`. If your
   change needs a device, add it under `tests/integration/`.
4. Make sure `pytest` passes locally and `ruff check` is clean.
5. Open the PR — fill out the template. Reference the issue.

## What we'd love help with

- New `open_settings` panels for OEM-specific settings activities
  (Samsung, Xiaomi, OnePlus, …).
- A `verify_state` helper that reuses `wait_for` semantics to assert a
  toggle is on/off after an action.
- Better OCR engines (Tesseract path improvements, language packs).
- A demo `.gif` for the README (drop into `assets/`).
- Sample agent prompts in `docs/agent_prompts.md` showing how to instruct
  different models (gpt-oss-20b, qwen3vl, Claude, GPT-4o, Gemini) to use the
  server well.
- More client config snippets in `examples/` (Continue.dev, Goose, Zed, …).

## Code of conduct

Be kind. Assume good faith. Disagree with ideas, not people. The
maintainer reserves the right to remove comments and contributors that
violate this principle.
