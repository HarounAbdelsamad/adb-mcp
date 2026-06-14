"""Tests for UI hierarchy XML parsing."""
from __future__ import annotations

from adb_mcp.ui.tree import parse_hierarchy

SETTINGS_FIXTURE = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.android.settings" content-desc="" checkable="false"
        checked="false" clickable="false" enabled="true" focusable="false"
        focused="false" scrollable="false" long-clickable="false"
        password="false" selected="false" bounds="[0,0][1080,1920]">
    <node index="0" text="Wi-Fi" resource-id="com.android.settings:id/wifi_title"
          class="android.widget.TextView" package="com.android.settings"
          content-desc="" checkable="false" checked="false" clickable="true"
          enabled="true" focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[0,100][1080,200]" />
    <node index="1" text="" resource-id="" class="android.widget.LinearLayout"
          package="com.android.settings" content-desc="Bluetooth settings"
          checkable="false" checked="false" clickable="true" enabled="true"
          focusable="true" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[0,200][1080,300]">
      <node index="0" text="Bluetooth" resource-id="com.android.settings:id/bt_title"
            class="android.widget.TextView" package="com.android.settings"
            content-desc="" checkable="false" checked="false" clickable="false"
            enabled="true" focusable="false" focused="false" scrollable="false"
            long-clickable="false" password="false" selected="false"
            bounds="[16,210][900,290]" />
    </node>
  </node>
</hierarchy>
"""


def test_parse_returns_nodes():
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    assert len(nodes) >= 2


def test_node_has_id():
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    ids = [n.id for n in nodes]
    assert ids == list(range(len(nodes))), "IDs must be monotonic from 0"


def test_wifi_node_parsed():
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    wifi = next((n for n in nodes if n.text == "Wi-Fi"), None)
    assert wifi is not None
    assert wifi.clickable is True
    assert wifi.resource_id == "com.android.settings:id/wifi_title"
    assert wifi.bounds["x"] == 0
    assert wifi.bounds["y"] == 100
    assert wifi.bounds["w"] == 1080
    assert wifi.bounds["h"] == 100
    assert wifi.center == {"x": 540, "y": 150}


def test_content_desc_node_parsed():
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    bt = next((n for n in nodes if n.content_desc == "Bluetooth settings"), None)
    assert bt is not None
    assert bt.clickable is True


def test_non_interactable_layout_excluded():
    # The root FrameLayout (clickable=false, no text/desc) should be filtered.
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    frame_layouts = [n for n in nodes if n.cls == "android.widget.FrameLayout"]
    assert len(frame_layouts) == 0, "Non-interactable layouts must be pruned"


def test_child_text_node_included_via_parent_semantics():
    # The inner "Bluetooth" TextView has text but clickable=false.
    # It should still appear because it has text.
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    bt_text = next((n for n in nodes if n.text == "Bluetooth"), None)
    assert bt_text is not None


def test_max_nodes_enforced():
    # Build a large hierarchy
    rows = "\n".join(
        f'<node index="{i}" text="Item {i}" resource-id="id/item{i}" '
        f'class="android.widget.TextView" package="com.test" content-desc="" '
        f'checkable="false" checked="false" clickable="true" enabled="true" '
        f'focusable="true" focused="false" scrollable="false" '
        f'long-clickable="false" password="false" selected="false" '
        f'bounds="[0,{i*50}][1080,{i*50+50}]" />'
        for i in range(200)
    )
    xml = f'<hierarchy rotation="0"><node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.test" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,9999]">{rows}</node></hierarchy>'
    nodes, truncated = parse_hierarchy(xml, max_nodes=50)
    assert len(nodes) <= 50
    assert truncated is True


def test_safe_prune_keeps_clickable():
    """Clickable nodes must survive pruning even with a tiny max_nodes budget."""
    rows = "\n".join(
        f'<node index="{i}" text="Item {i}" resource-id="id/item{i}" '
        f'class="android.widget.TextView" package="com.test" content-desc="" '
        f'checkable="false" checked="false" clickable="true" enabled="true" '
        f'focusable="true" focused="false" scrollable="false" '
        f'long-clickable="false" password="false" selected="false" '
        f'bounds="[0,{i*50}][1080,{i*50+50}]" />'
        for i in range(30)
    )
    xml = f'<hierarchy rotation="0"><node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.test" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,9999]">{rows}</node></hierarchy>'
    nodes, _ = parse_hierarchy(xml, max_nodes=10)
    # All retained nodes must be clickable (they all are in this fixture)
    for n in nodes:
        assert n.clickable or n.long_clickable or n.scrollable, "Non-actionable node survived pruning"


def test_to_dict_shape():
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    d = nodes[0].to_dict()
    for key in ("id", "class", "text", "content_desc", "resource_id", "bounds", "center",
                "clickable", "focusable", "enabled", "parent", "children"):
        assert key in d, f"Missing key: {key}"


def test_to_compact_shape():
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    c = nodes[0].to_compact()
    assert "id" in c
    assert "class" in c
    # class should be shortened to last segment
    assert "." not in c["class"]


def test_nodes_to_text_list():
    from adb_mcp.ui.tree import nodes_to_text_list
    nodes, _ = parse_hierarchy(SETTINGS_FIXTURE)
    listing = nodes_to_text_list(nodes)
    assert "Wi-Fi" in listing
    # Each line starts with a node id
    for line in listing.splitlines():
        assert line[0].isdigit()
