from __future__ import annotations

from adb_mcp.tools.apps import (
    _derive_app_name,
    _find_by_selectors,
    _find_first_search_result,
    _find_overflow_menu,
    _find_search_field,
    _find_searched_apps_container,
    _first_app_in_subtree,
    _foreground_needles,
    _nodes_by_id,
)
from adb_mcp.ui.tree import UiNode


def _node(
    nid: int,
    text: str = "",
    desc: str = "",
    y: int = 100,
    clickable: bool = True,
    cls: str = "android.widget.TextView",
    resource_id: str = "",
    package: str = "com.sec.android.app.launcher",
    parent: int | None = None,
    children: list[int] | None = None,
) -> UiNode:
    return UiNode(
        id=nid,
        cls=cls,
        text=text,
        content_desc=desc,
        resource_id=resource_id,
        package=package,
        bounds={"x": 0, "y": y, "w": 100, "h": 50},
        center={"x": 50, "y": y + 25},
        clickable=clickable,
        long_clickable=False,
        scrollable=False,
        focusable=clickable,
        focused=False,
        enabled=True,
        selected=False,
        checked=None,
        parent=parent,
        children=children or [],
    )


def test_derive_app_name_skips_locale_pack():
    assert _derive_app_name("com.samsung.android.bixby.ondevice.dede") == "Bixby"


def test_derive_app_name_from_settings():
    assert _derive_app_name("com.android.settings") == "Settings"


def test_find_search_field_prefers_search_label():
    nodes = [
        _node(0, text="Apps", y=50),
        _node(1, text="Search", y=120, cls="android.widget.EditText"),
    ]
    found = _find_search_field(nodes)
    assert found is not None
    assert found.text == "Search"


def test_find_searched_apps_container_uses_parent_section():
    nodes = [
        _node(0, cls="android.widget.LinearLayout", y=200, clickable=False, children=[1, 2, 3]),
        _node(1, text="Searched Apps", y=200, clickable=False, parent=0),
        _node(2, text="Bixby", y=260, parent=0),
        _node(3, text="Bixby Vision", y=320, parent=0),
    ]
    container = _find_searched_apps_container(nodes)
    assert container is not None
    assert container.id == 0


def test_first_app_in_subtree_skips_header():
    nodes = [
        _node(0, cls="android.widget.LinearLayout", y=200, clickable=False, children=[1, 2]),
        _node(1, text="Searched Apps", y=200, clickable=False, parent=0),
        _node(2, text="Bixby", y=260, parent=0),
    ]
    by_id = _nodes_by_id(nodes)
    result = _first_app_in_subtree(nodes[0], by_id)
    assert result is not None
    assert result.text == "Bixby"


def test_find_first_search_result_prefers_searched_apps_container():
    nodes = [
        _node(0, text="Search", y=100, cls="android.widget.EditText", clickable=False),
        _node(1, cls="android.widget.LinearLayout", y=200, clickable=False, children=[2, 3, 4]),
        _node(2, text="Searched Apps", y=200, clickable=False, parent=1),
        _node(3, text="Bixby", y=260, parent=1),
        _node(4, text="Recents", y=2200, package="com.android.systemui"),
    ]
    found = _find_first_search_result(nodes, "Bixby", search_y=125)
    assert found is not None
    assert found.text == "Bixby"


def test_find_by_selectors_finds_settings():
    nodes = [
        _node(0, text="Home", y=100),
        _node(1, text="Settings", y=200),
    ]
    found = _find_by_selectors(nodes, [{"text": "Settings"}])
    assert found is not None
    assert found.text == "Settings"


def test_find_overflow_menu_matches_more_options():
    nodes = [
        _node(0, desc="More options", y=50, cls="android.widget.ImageButton"),
        _node(1, text="Settings", y=200),
    ]
    found = _find_overflow_menu(nodes)
    assert found is not None
    assert found.content_desc == "More options"


def test_foreground_needles_includes_bixby_package_hints():
    needles = _foreground_needles("Bixby", label="Bixby")
    assert "com.samsung.android.bixby" in needles
    assert "Bixby" in needles


def test_find_first_search_result_uses_section_below_header():
    nodes = [
        _node(0, text="Search", y=100, cls="android.widget.EditText", clickable=False),
        _node(1, text="Searched Apps", y=200, clickable=False),
        _node(2, text="Bixby", y=280),
        _node(3, text="Recents", y=2200, package="com.android.systemui"),
    ]
    found = _find_first_search_result(nodes, "Bixby", search_y=125)
    assert found is not None
    assert found.text == "Bixby"
