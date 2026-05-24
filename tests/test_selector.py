"""Tests for semantic selector resolution."""
from __future__ import annotations

import pytest

from adb_mcp.errors import AgentError, ErrorCode
from adb_mcp.ui.selector import _score_node, resolve
from adb_mcp.ui.tree import parse_hierarchy
from adb_mcp.util.cache import SnapshotCache

FIXTURE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.android.settings" content-desc="" checkable="false" checked="false"
        clickable="false" enabled="true" focusable="false" focused="false"
        scrollable="false" long-clickable="false" password="false" selected="false"
        bounds="[0,0][1080,1920]">
    <node index="0" text="Network &amp; internet" resource-id="com.android.settings:id/network"
          class="android.widget.RelativeLayout" package="com.android.settings"
          content-desc="" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[0,100][1080,200]" />
    <node index="1" text="Wi-Fi" resource-id="com.android.settings:id/wifi"
          class="android.widget.TextView" package="com.android.settings"
          content-desc="" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[0,200][1080,300]" />
    <node index="2" text="Wi-Fi calling" resource-id="com.android.settings:id/wifi_calling"
          class="android.widget.TextView" package="com.android.settings"
          content-desc="" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[0,300][1080,400]" />
    <node index="3" text="Connect" resource-id="com.android.settings:id/btn_connect"
          class="android.widget.Button" package="com.android.settings"
          content-desc="Connect to network" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[400,800][700,900]" />
  </node>
</hierarchy>
"""

SERIAL = "test-device"


def _make_cache(nodes):
    cache = SnapshotCache()
    cache.put(SERIAL, nodes, "", None)
    return cache


def _patch_cache(monkeypatch, cache):
    import adb_mcp.ui.selector as sel_mod
    monkeypatch.setattr(sel_mod, "snapshot_cache", cache)


def test_resolve_by_text(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    res = resolve({"text": "Wi-Fi"}, SERIAL)
    assert res.strategy in ("text", "resource_id", "composite")
    assert res.node is not None
    assert res.node.text == "Wi-Fi"


def test_resolve_by_resource_id(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    res = resolve({"resource_id": "com.android.settings:id/btn_connect"}, SERIAL)
    assert res.node is not None
    assert res.node.resource_id == "com.android.settings:id/btn_connect"


def test_resolve_by_content_desc(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    res = resolve({"content_desc": "Connect to network"}, SERIAL)
    assert res.node is not None
    assert "Connect" in res.node.text


def test_resolve_by_text_contains(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    res = resolve({"text_contains": "Network"}, SERIAL)
    assert res.node is not None
    assert "Network" in res.node.text


def test_resolve_by_som_id(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    cache = _make_cache(nodes)
    _patch_cache(monkeypatch, cache)
    # Pick any node id
    target_id = nodes[1].id
    res = resolve({"id": target_id}, SERIAL)
    assert res.strategy == "id"
    assert res.node.id == target_id


def test_resolve_no_match_raises(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    with pytest.raises(AgentError) as exc_info:
        resolve({"text": "ThisTextDoesNotExist12345"}, SERIAL)
    assert exc_info.value.code == ErrorCode.SELECTOR_NO_MATCH


def test_resolve_ambiguous_raises(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    # "Wi-Fi" substring matches both "Wi-Fi" and "Wi-Fi calling"
    with pytest.raises(AgentError) as exc_info:
        resolve({"text_contains": "Wi-Fi"}, SERIAL)
    assert exc_info.value.code in (ErrorCode.SELECTOR_AMBIGUOUS, ErrorCode.SELECTOR_NO_MATCH)


def test_resolve_index_disambiguates(monkeypatch):
    nodes = parse_hierarchy(FIXTURE_XML)
    _patch_cache(monkeypatch, _make_cache(nodes))
    # Exact text "Wi-Fi" is unique so index should work
    res = resolve({"text": "Wi-Fi", "index": 0}, SERIAL)
    assert res.node is not None


def test_score_resource_id_highest():
    nodes = parse_hierarchy(FIXTURE_XML)
    connect = next(n for n in nodes if n.resource_id == "com.android.settings:id/btn_connect")
    s_rid = _score_node(connect, {"resource_id": "com.android.settings:id/btn_connect"})
    s_text = _score_node(connect, {"text": "Connect"})
    assert s_rid > s_text, "resource_id match should outscore text match"


def test_no_snapshot_with_coords_fallback(monkeypatch):
    import adb_mcp.ui.selector as sel_mod
    monkeypatch.setattr(sel_mod, "snapshot_cache", SnapshotCache())
    res = resolve({}, "no-device", fallback_x=100, fallback_y=200)
    assert res.strategy == "coords"
    assert res.x == 100 and res.y == 200
