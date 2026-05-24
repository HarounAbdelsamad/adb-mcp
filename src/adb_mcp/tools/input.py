from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..device import device_manager
from ..errors import AgentError, ErrorCode, tool_safe
from ..ui.selector import resolve
from ..util.cache import snapshot_cache

log = logging.getLogger(__name__)

# Map friendly key names → uiautomator2 key names / Android keycodes
_KEY_MAP: dict[str, str] = {
    "back": "back",
    "home": "home",
    "menu": "menu",
    "enter": "enter",
    "delete": "del",
    "backspace": "del",
    "recent": "recent",
    "power": "power",
    "volume_up": "volume_up",
    "volume_down": "volume_down",
    "camera": "camera",
    "search": "search",
    "tab": "tab",
    "space": "space",
    "escape": "escape",
    "dpad_up": "dpad_up",
    "dpad_down": "dpad_down",
    "dpad_left": "dpad_left",
    "dpad_right": "dpad_right",
    "dpad_center": "dpad_center",
}


def _serial(device_serial: str | None) -> str:
    return device_manager.resolve_adb(device_serial).serial


@tool_safe
def _tap(
    selector: dict[str, Any] | None = None,
    x: int | None = None,
    y: int | None = None,
    long_press: bool = False,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    d = device_manager.resolve_u2(serial)

    if selector:
        res = resolve(selector, serial, fallback_x=x, fallback_y=y)
        tx, ty = res.x, res.y
        strategy = res.strategy
        node_info = res.node.to_dict() if res.node else None
    elif x is not None and y is not None:
        tx, ty = x, y
        strategy = "coords"
        node_info = None
    else:
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            "Provide either selector or x,y coordinates.",
        )

    if long_press:
        d.long_click(tx, ty)
    else:
        d.click(tx, ty)

    # Invalidate cache so next get_screen is fresh
    snapshot_cache.invalidate(serial)

    return {
        "ok": True,
        "resolved": {"strategy": strategy, "node": node_info},
        "x": tx,
        "y": ty,
    }


@tool_safe
def _swipe(
    direction: str | None = None,
    from_selector: dict[str, Any] | None = None,
    to_selector: dict[str, Any] | None = None,
    x1: int | None = None,
    y1: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    duration_ms: int = 300,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    d = device_manager.resolve_u2(serial)

    if direction:
        direction = direction.lower()
        size = d.window_size()
        w, h = size
        cx, cy = w // 2, h // 2
        dist = min(w, h) // 3
        dirs = {
            "up": (cx, cy + dist, cx, cy - dist),
            "down": (cx, cy - dist, cx, cy + dist),
            "left": (cx + dist, cy, cx - dist, cy),
            "right": (cx - dist, cy, cx + dist, cy),
        }
        if direction not in dirs:
            raise AgentError(
                ErrorCode.INVALID_ARGUMENT,
                f"direction must be one of {list(dirs.keys())}",
            )
        sx1, sy1, sx2, sy2 = dirs[direction]
    elif from_selector and to_selector:
        from_res = resolve(from_selector, serial)
        to_res = resolve(to_selector, serial)
        sx1, sy1 = from_res.x, from_res.y
        sx2, sy2 = to_res.x, to_res.y
    elif x1 is not None and y1 is not None and x2 is not None and y2 is not None:
        sx1, sy1, sx2, sy2 = x1, y1, x2, y2
    else:
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            "Provide direction, from_selector+to_selector, or x1,y1,x2,y2.",
        )

    d.swipe(sx1, sy1, sx2, sy2, duration=duration_ms / 1000)
    snapshot_cache.invalidate(serial)
    return {"ok": True, "from": {"x": sx1, "y": sy1}, "to": {"x": sx2, "y": sy2}}


@tool_safe
def _type_text(
    text: str,
    selector: dict[str, Any] | None = None,
    clear: bool = False,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    d = device_manager.resolve_u2(serial)
    node_info = None

    if selector:
        res = resolve(selector, serial)
        el = d(resourceId=res.node.resource_id) if res.node and res.node.resource_id else None
        if el and el.exists(timeout=2):
            if clear:
                el.clear_text()
            el.set_text(text)
            node_info = res.node.to_dict() if res.node else None
        else:
            # fallback: click position then send_keys
            d.click(res.x, res.y)
            time.sleep(0.3)
            if clear:
                d.clear_text()
            d.send_keys(text)
            node_info = res.node.to_dict() if res.node else None
    else:
        if clear:
            d.clear_text()
        d.send_keys(text)

    snapshot_cache.invalidate(serial)
    return {"ok": True, "focused_node": node_info}


@tool_safe
def _press_key(
    key: str,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    d = device_manager.resolve_u2(serial)
    mapped = _KEY_MAP.get(key.lower(), key.lower())
    d.press(mapped)
    snapshot_cache.invalidate(serial)
    return {"ok": True, "key": key}


def register(mcp: FastMCP) -> None:
    mcp.tool(
        name="tap",
        description=(
            "Tap an element. Prefer selector (semantic) over x,y coordinates. "
            "Selector keys: id (SoM number from get_screen), text, text_contains, resource_id, content_desc, class, index. "
            "Set long_press=true for long-tap. Returns resolved strategy and coordinates."
        ),
    )(_tap)

    mcp.tool(
        name="swipe",
        description=(
            "Swipe on the screen. Use direction='up'|'down'|'left'|'right' for scroll gestures, "
            "or from_selector+to_selector for drag, or x1,y1,x2,y2 for precise swipe. "
            "duration_ms controls speed (higher = slower)."
        ),
    )(_swipe)

    mcp.tool(
        name="type_text",
        description=(
            "Type text into the focused field or a specific element. "
            "Use selector to focus the target element first. "
            "Set clear=true to wipe existing text before typing."
        ),
    )(_type_text)

    mcp.tool(
        name="press_key",
        description=(
            "Press a hardware or system key. "
            "Common keys: back, home, enter, delete, recent, power, volume_up, volume_down, tab, search. "
            "Use 'back' to dismiss dialogs or navigate back."
        ),
    )(_press_key)
