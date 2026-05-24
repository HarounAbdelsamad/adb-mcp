from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class UiNode:
    id: int
    cls: str
    text: str
    content_desc: str
    resource_id: str
    package: str
    bounds: dict           # {x, y, w, h}
    center: dict           # {x, y}
    clickable: bool
    long_clickable: bool
    scrollable: bool
    focusable: bool
    focused: bool
    enabled: bool
    selected: bool
    checked: bool | None
    parent: int | None
    children: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.cls,
            "text": self.text,
            "content_desc": self.content_desc,
            "resource_id": self.resource_id,
            "package": self.package,
            "bounds": self.bounds,
            "center": self.center,
            "clickable": self.clickable,
            "long_clickable": self.long_clickable,
            "scrollable": self.scrollable,
            "focusable": self.focusable,
            "focused": self.focused,
            "enabled": self.enabled,
            "selected": self.selected,
            "checked": self.checked,
            "parent": self.parent,
            "children": self.children,
        }


def _parse_bounds(bounds_str: str) -> tuple[int, int, int, int]:
    """Parse '[x1,y1][x2,y2]' → (x1, y1, x2, y2)."""
    parts = bounds_str.replace("][", ",").strip("[]").split(",")
    x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    return x1, y1, x2, y2


def _bool_attr(elem: ET.Element, attr: str) -> bool:
    return elem.get(attr, "false").lower() == "true"


def _checked_attr(elem: ET.Element) -> bool | None:
    val = elem.get("checked")
    if val is None:
        return None
    return val.lower() == "true"


def _is_interactable(elem: ET.Element) -> bool:
    clickable = elem.get("clickable", "false").lower() == "true"
    long_clickable = elem.get("long-clickable", "false").lower() == "true"
    scrollable = elem.get("scrollable", "false").lower() == "true"
    text = (elem.get("text") or "").strip()
    desc = (elem.get("content-desc") or "").strip()
    return clickable or long_clickable or scrollable or bool(text) or bool(desc)


def parse_hierarchy(xml_str: str, max_nodes: int = 80) -> list[UiNode]:
    """Parse uiautomator XML dump into a list of UiNode, DFS order."""
    root = ET.fromstring(xml_str)
    nodes: list[UiNode] = []
    _id_counter = [0]
    _elem_to_id: dict[int, int] = {}

    def walk(elem: ET.Element, parent_id: int | None) -> int | None:
        if not _is_interactable(elem):
            # Still recurse to find children, but don't emit a node.
            for child in elem:
                walk(child, parent_id)
            return None

        node_id = _id_counter[0]
        _id_counter[0] += 1
        _elem_to_id[id(elem)] = node_id

        bounds_str = elem.get("bounds", "[0,0][0,0]")
        x1, y1, x2, y2 = _parse_bounds(bounds_str)
        w, h = x2 - x1, y2 - y1

        node = UiNode(
            id=node_id,
            cls=elem.get("class", ""),
            text=(elem.get("text") or "").strip(),
            content_desc=(elem.get("content-desc") or "").strip(),
            resource_id=elem.get("resource-id", ""),
            package=elem.get("package", ""),
            bounds={"x": x1, "y": y1, "w": w, "h": h},
            center={"x": x1 + w // 2, "y": y1 + h // 2},
            clickable=_bool_attr(elem, "clickable"),
            long_clickable=_bool_attr(elem, "long-clickable"),
            scrollable=_bool_attr(elem, "scrollable"),
            focusable=_bool_attr(elem, "focusable"),
            focused=_bool_attr(elem, "focused"),
            enabled=_bool_attr(elem, "enabled"),
            selected=_bool_attr(elem, "selected"),
            checked=_checked_attr(elem),
            parent=parent_id,
        )
        nodes.append(node)

        child_ids: list[int] = []
        for child in elem:
            cid = walk(child, node_id)
            if cid is not None:
                child_ids.append(cid)
        node.children = child_ids

        return node_id

    walk(root, None)

    return _prune(nodes, max_nodes)


def _prune(nodes: list[UiNode], max_nodes: int) -> list[UiNode]:
    if len(nodes) <= max_nodes:
        return nodes

    def score(n: UiNode) -> int:
        s = 0
        if n.clickable:
            s += 10
        if n.text:
            s += 6
        if n.content_desc:
            s += 4
        if n.focusable:
            s += 2
        area = n.bounds["w"] * n.bounds["h"]
        s += min(area // 10000, 5)
        return s

    ranked = sorted(nodes, key=score, reverse=True)
    kept_ids = {n.id for n in ranked[:max_nodes]}
    pruned = [n for n in nodes if n.id in kept_ids]

    # Fix parent/children to only reference kept nodes.
    for n in pruned:
        n.children = [c for c in n.children if c in kept_ids]
        if n.parent is not None and n.parent not in kept_ids:
            n.parent = None

    return pruned
