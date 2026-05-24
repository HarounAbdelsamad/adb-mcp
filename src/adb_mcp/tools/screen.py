from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..config import cfg
from ..device import device_manager
from ..errors import AgentError, ErrorCode, tool_safe
from ..ui.ocr import merge_with_tree, run_ocr
from ..ui.som import annotate_to_base64
from ..ui.tree import parse_hierarchy
from ..util.cache import snapshot_cache
from ..util.screenshot import capture, downscale, to_base64_png

log = logging.getLogger(__name__)


def _get_serial(d: str | None) -> str:
    return device_manager.resolve_adb(d).serial


def _build_screen_payload(
    serial: str,
    mode: str,
    include_ocr: bool,
    max_nodes: int,
) -> dict[str, Any]:
    d = device_manager.resolve_u2(serial)

    xml = d.dump_hierarchy(compressed=False)
    nodes = parse_hierarchy(xml, max_nodes=max_nodes)

    # Screenshot (always capture; we need it for SoM or to pass to OCR)
    img = capture(d)
    w_orig, h_orig = img.size
    img_small = downscale(img)
    w_small, h_small = img_small.size
    scale = w_small / w_orig if w_orig else 1.0

    ocr_spans: list[dict] = []
    if include_ocr and cfg.ocr_enabled and mode in ("text", "both"):
        raw_spans = run_ocr(img_small)
        # Scale OCR bboxes back to original coords for consistency with tree bounds
        if scale != 1.0:
            for s in raw_spans:
                b = s["bbox"]
                s["bbox"] = {
                    "x": int(b["x"] / scale),
                    "y": int(b["y"] / scale),
                    "w": int(b["w"] / scale),
                    "h": int(b["h"] / scale),
                }
        ocr_spans = merge_with_tree(raw_spans, nodes)

    snap = snapshot_cache.put(serial, nodes, xml, img)

    payload: dict[str, Any] = {
        "ok": True,
        "snapshot_id": snap.snapshot_id,
        "screen": {"w": w_orig, "h": h_orig},
        "tree": [n.to_dict() for n in nodes],
    }

    if include_ocr and mode in ("text", "both"):
        payload["ocr"] = ocr_spans

    if mode in ("vision", "both"):
        if cfg.som_default_enabled:
            payload["image_b64"] = annotate_to_base64(img_small, nodes, scale)
        else:
            payload["image_b64"] = to_base64_png(img_small)
        payload["image_mime"] = "image/png"

    return payload


@tool_safe
def _get_screen(
    mode: str = "both",
    include_ocr: bool = True,
    max_nodes: int = 80,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _get_serial(device_serial)
    return _build_screen_payload(serial, mode, include_ocr, max_nodes)


@tool_safe
def _wait_for(
    selector: dict[str, Any],
    condition: str = "appear",
    timeout_ms: int = 8000,
    poll_ms: int = 300,
    device_serial: str | None = None,
) -> dict[str, Any]:

    serial = _get_serial(device_serial)
    deadline = time.monotonic() + timeout_ms / 1000
    started = time.monotonic()

    while True:
        # Refresh hierarchy
        d = device_manager.resolve_u2(serial)
        try:
            xml = d.dump_hierarchy(compressed=False)
        except Exception as exc:
            raise AgentError(ErrorCode.UIAUTOMATOR_NOT_READY, str(exc)) from exc

        nodes = parse_hierarchy(xml)
        snapshot_cache.put(serial, nodes, xml)

        found = False
        matched_node = None
        for node in nodes:
            from ..ui.selector import _score_node
            if _score_node(node, selector) > 0:
                found = True
                matched_node = node
                break

        if condition == "appear" and found:
            return {
                "ok": True,
                "matched": True,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "node": matched_node.to_dict() if matched_node else None,
            }
        if condition == "disappear" and not found:
            return {
                "ok": True,
                "matched": True,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "node": None,
            }
        if condition == "text_change" and found:
            # Return when the selector matches — caller can compare text externally.
            return {
                "ok": True,
                "matched": True,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "node": matched_node.to_dict() if matched_node else None,
            }

        if time.monotonic() >= deadline:
            return {
                "ok": True,
                "matched": False,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "node": None,
            }

        time.sleep(poll_ms / 1000)


def register(mcp: FastMCP) -> None:
    mcp.tool(
        name="get_screen",
        description=(
            "Capture current screen. Returns UI element tree (JSON), OCR text spans, "
            "and optionally a Set-of-Mark numbered screenshot. "
            "Use mode='text' for text-only models, mode='vision' for vision models, mode='both' for both. "
            "Element IDs in the tree match the numbered badges in the image — pass id:N to tap()."
        ),
    )(_get_screen)

    mcp.tool(
        name="wait_for",
        description=(
            "Wait until a UI element appears, disappears, or changes. "
            "Essential after navigation actions in onboarding flows. "
            "Selector keys: text, text_contains, resource_id, content_desc, class, id (SoM number). "
            "Returns matched:true/false and the matched node if found."
        ),
    )(_wait_for)
