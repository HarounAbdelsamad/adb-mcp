from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import apps, diag, screen, settings
from . import input as _input


def register_all(mcp: FastMCP) -> None:
    for mod in (screen, _input, apps, settings, diag):
        mod.register(mcp)
