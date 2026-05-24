"""Tests for Set-of-Mark screenshot annotator."""
from __future__ import annotations

import base64
import io

from PIL import Image

from adb_mcp.ui.som import _PALETTE, annotate, annotate_to_base64
from adb_mcp.ui.tree import parse_hierarchy

SIMPLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.test" content-desc="" checkable="false" checked="false"
        clickable="false" enabled="true" focusable="false" focused="false"
        scrollable="false" long-clickable="false" password="false" selected="false"
        bounds="[0,0][1080,1920]">
    <node index="0" text="Button A" resource-id="com.test:id/btn_a"
          class="android.widget.Button" package="com.test"
          content-desc="" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[100,100][500,200]" />
    <node index="1" text="Button B" resource-id="com.test:id/btn_b"
          class="android.widget.Button" package="com.test"
          content-desc="" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[100,250][500,350]" />
  </node>
</hierarchy>
"""


def _make_image(w: int = 1080, h: int = 1920) -> Image.Image:
    return Image.new("RGB", (w, h), color=(240, 240, 240))


def test_annotate_returns_image():
    nodes = parse_hierarchy(SIMPLE_XML)
    img = _make_image()
    result = annotate(img, nodes)
    assert isinstance(result, Image.Image)
    assert result.size == img.size


def test_annotate_does_not_modify_original():
    nodes = parse_hierarchy(SIMPLE_XML)
    img = _make_image()
    original_pixel = img.getpixel((0, 0))
    annotate(img, nodes)
    assert img.getpixel((0, 0)) == original_pixel, "Original image must not be mutated"


def test_annotate_to_base64_valid_png():
    nodes = parse_hierarchy(SIMPLE_XML)
    img = _make_image()
    b64 = annotate_to_base64(img, nodes)
    decoded = base64.b64decode(b64)
    reopened = Image.open(io.BytesIO(decoded))
    assert reopened.format == "PNG"


def test_palette_cycles():
    """IDs use palette[id % len(palette)] so different IDs get different colors."""
    assert len(_PALETTE) == 8
    colors_used = [_PALETTE[i % len(_PALETTE)] for i in range(16)]
    # First 8 and second 8 should repeat
    assert colors_used[:8] == colors_used[8:]


def test_scale_parameter():
    """scale != 1.0 should still produce a valid image."""
    nodes = parse_hierarchy(SIMPLE_XML)
    img = _make_image(540, 960)  # half-size
    result = annotate(img, nodes, scale=0.5)
    assert isinstance(result, Image.Image)


def test_empty_nodes_returns_copy():
    img = _make_image()
    result = annotate(img, [])
    assert result.size == img.size
