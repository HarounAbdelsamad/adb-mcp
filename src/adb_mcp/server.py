from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from .config import cfg
from .tools import register_all

logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))
log = logging.getLogger(__name__)

# Tell adbutils which adb binary to use
os.environ.setdefault("ADBUTILS_ADB_PATH", cfg.adb_path)


def build_server() -> FastMCP:
    mcp = FastMCP(
        "adb-mcp",
        instructions=(
            # ── Orientation ──────────────────────────────────────────────────
            "You control an Android device via ADB. "
            "Always call list_devices first if you are unsure whether a device is connected. "

            # ── Screen observation ────────────────────────────────────────────
            "Call get_screen(mode='text') to see the current UI before acting. "
            "The 'tree' field is a numbered text list — each line is "
            "'<id> [ClassName] \"label\"'. "
            "Use those id numbers to tap: tap(selector={\"id\": 12}). "
            "Prefer semantic selectors (text, content_desc, resource_id) over raw coordinates; "
            "only fall back to x/y when no semantic field is available. "

            # ── tap / swipe / type_text observe loop ─────────────────────────
            "tap() and swipe() return screen_changed and the new screen tree by default. "
            "Check screen_changed: if False, the action did not have the expected effect — "
            "re-read the screen and try a different selector or scroll to reveal the target. "
            "Only call get_screen again separately when you need a fresh baseline. "

            # ── Truncation ────────────────────────────────────────────────────
            "If the response contains truncated:true, some elements were pruned. "
            "Call swipe('up') or swipe('down') to reveal more, then re-read the screen. "

            # ── Settings ──────────────────────────────────────────────────────
            "Use open_settings(panel='...') to jump directly into Android system settings. "
            "To reach an app's own settings: "
            "(1) launch_app(app_name='...'), then "
            "(2) navigate_in_app_settings() — it tries Settings directly, "
            "then Menu / More options / View more, then Settings. "

            # ── App launch ────────────────────────────────────────────────────
            "launch_app(app_name='...') searches the launcher if direct package launch fails. "
            "Check foreground:true in the response before proceeding. "

            # ── Ambiguous selectors ───────────────────────────────────────────
            "If a selector returns SELECTOR_AMBIGUOUS, the response includes a 'candidates' "
            "list with id numbers. Re-tap the correct one with tap(selector={\"id\": N}). "

            # ── Goal confirmation ─────────────────────────────────────────────
            "After completing a task, confirm the outcome from the returned screen tree "
            "or a final get_screen. Report success only when the desired state is visible."
        ),
    )
    register_all(mcp)
    log.info("adb-mcp server built with %d tools", len(mcp._tool_manager._tools))
    return mcp
