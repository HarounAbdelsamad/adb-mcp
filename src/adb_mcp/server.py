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
            "Advanced ADB server for Android automation. "
            "Start with list_devices to confirm connectivity. "
            "Use get_screen to see the current UI — it returns both a JSON element tree and "
            "(optionally) a numbered screenshot. Tap elements by their id number or semantic "
            "selector (text, resource_id, content_desc) rather than raw coordinates. "
            "Use open_settings to jump directly to specific settings panels."
        ),
    )
    register_all(mcp)
    log.info("adb-mcp server built with %d tools", len(mcp._tool_manager._tools))
    return mcp
