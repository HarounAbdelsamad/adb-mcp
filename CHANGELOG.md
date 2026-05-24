# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-24

### Added

- Initial release.
- 15 semantic ADB tools tuned for small-LLM tool calling:
  `list_devices`, `device_info`, `get_screen`, `wait_for`, `tap`, `swipe`,
  `type_text`, `press_key`, `launch_app`, `list_packages`, `app_info`,
  `open_settings`, `grant_permission`, `get_logcat`, `dumpsys_query`.
- Dual-path screen understanding via `get_screen`:
  - **Text path** — accessibility tree + PaddleOCR spans as JSON, for
    text-only models like gpt-oss-20b.
  - **Vision path** — Set-of-Mark numbered overlay PNG, for vision models
    like qwen3vl. Element IDs are shared across both paths.
- Semantic selector resolution (`resource_id`, `text`, `text_contains`,
  `content_desc`, `class`, SoM `id`, `index`) with scoring and structured
  ambiguity errors that include the top candidate list.
- Snapshot cache so SoM ids resolve in O(1) on the next `tap`/`wait_for`.
- 25-panel `open_settings` deep-link map for Android settings/onboarding
  flows.
- `@tool_safe` decorator that converts exceptions into
  `{ok: false, error_code, message, hint}` payloads so small models can
  self-correct.
- Multi-device handling with `device_serial` param on every tool.
- Configuration via `config.yaml` and `ADB_MCP_*` env vars.
- 24 unit tests covering tree parsing, selector scoring/ambiguity, and SoM
  rendering.
- Live-device integration test suite (auto-skips when no device attached).
- Support for both `pip` and `uv` workflows.
