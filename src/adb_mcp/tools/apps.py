from __future__ import annotations

import logging
import re
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..config import cfg
from ..device import device_manager
from ..errors import AgentError, ErrorCode, tool_safe
from ..ui.selector import _score_node
from ..ui.tree import parse_hierarchy
from ..util.cache import snapshot_cache

log = logging.getLogger(__name__)

_SKIP_NAME_PARTS = frozenset({
    "android", "app", "mobile", "agent", "service", "plugin",
    "samsung", "google", "com", "ondevice", "dede", "enus", "en", "de",
})


def _serial(device_serial: str | None) -> str:
    return device_manager.resolve_adb(device_serial).serial


def _derive_app_name(package: str) -> str:
    """Best-effort human label from a package id for launcher search."""
    for part in reversed(package.split(".")):
        token = part.lower()
        if token in _SKIP_NAME_PARTS or len(token) <= 2:
            continue
        return part.replace("_", " ").title()
    return package.rsplit(".", 1)[-1].replace("_", " ").title()


_APP_PACKAGE_HINTS: dict[str, list[str]] = {
    "bixby": ["com.samsung.android.bixby", "bixby.agent", "bixbyagent"],
}


def _current_focus(adb_dev) -> str:
    return adb_dev.shell("dumpsys window windows | grep mCurrentFocus")


def _resumed_activity(adb_dev) -> str:
    try:
        return adb_dev.shell(
            "dumpsys activity activities | grep -E 'mResumedActivity|mFocusedApp'"
        )
    except Exception:
        return ""


def _foreground_needles(
    app_name: str = "",
    package: str = "",
    label: str = "",
) -> list[str]:
    needles: list[str] = []
    for value in (app_name, package, label):
        if value:
            needles.append(value)
    hints = _APP_PACKAGE_HINTS.get(app_name.lower().strip(), [])
    needles.extend(hints)
    if app_name:
        needles.append(app_name.lower().replace(" ", ""))
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(n for n in needles if n))


def _is_foreground(adb_dev, *needles: str) -> bool:
    haystack = f"{_current_focus(adb_dev)}\n{_resumed_activity(adb_dev)}".lower()
    return any(n.lower() in haystack for n in needles if n)


def _wait_for_foreground(
    adb_dev,
    *needles: str,
    timeout_ms: int | None = None,
    poll_ms: int = 400,
) -> bool:
    """Poll until the app appears in focus or the launch timeout expires."""
    if not needles:
        return False
    budget_s = (timeout_ms if timeout_ms is not None else cfg.tool_timeouts_ms.launch_app) / 1000
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        if _is_foreground(adb_dev, *needles):
            return True
        time.sleep(poll_ms / 1000)
    return _is_foreground(adb_dev, *needles)


def _capture_nodes(serial: str, max_nodes: int = 120) -> list:
    d = device_manager.resolve_u2(serial)
    xml = d.dump_hierarchy(compressed=False)
    nodes, _ = parse_hierarchy(xml, max_nodes=max_nodes)
    snapshot_cache.put(serial, nodes, xml)
    return nodes


def _nodes_by_id(nodes: list) -> dict[int, Any]:
    return {node.id: node for node in nodes}


def _is_searched_apps_header(node: Any) -> bool:
    label = f"{node.text} {node.content_desc}".strip().lower()
    return (
        "searched apps" in label
        or "gesuchte apps" in label
        or label == "searched apps"
        or label == "gesuchte apps"
    )


_EXCLUDED_RESULT_LABELS = frozenset({
    "search", "apps", "recents", "back", "home", "close", "clear", "cancel",
})


def _is_launcher_app_result(node: Any) -> bool:
    if not (node.clickable or node.long_clickable):
        return False
    label = (node.text or node.content_desc or "").strip()
    if not label:
        return False
    label_lower = label.lower()
    if label_lower in _EXCLUDED_RESULT_LABELS:
        return False
    if _is_searched_apps_header(node):
        return False
    # Navigation bar lives in System UI — never a searched app row.
    if node.package == "com.android.systemui":
        return False
    return True


def _collect_descendants(node_id: int, by_id: dict[int, Any]) -> list[Any]:
    node = by_id.get(node_id)
    if node is None:
        return []
    collected: list[Any] = []
    for child_id in node.children:
        child = by_id.get(child_id)
        if child is None:
            continue
        collected.append(child)
        collected.extend(_collect_descendants(child_id, by_id))
    return collected


def _first_app_in_subtree(root: Any, by_id: dict[int, Any]) -> Any | None:
    """Return the first launcher app row in DFS order under root."""
    for node in _collect_descendants(root.id, by_id):
        if _is_launcher_app_result(node):
            return node
    if _is_launcher_app_result(root):
        return root
    return None


def _find_searched_apps_container(nodes: list) -> Any | None:
    """Find the ViewGroup that owns the Searched Apps section, if exposed in the tree."""
    by_id = _nodes_by_id(nodes)
    for node in nodes:
        if not _is_searched_apps_header(node):
            continue
        # Prefer the parent section container when the header is a child label.
        if node.parent is not None:
            parent = by_id.get(node.parent)
            if parent is not None:
                return parent
        return node
    for node in nodes:
        rid = node.resource_id.lower()
        if "searched" in rid and ("app" in rid or "result" in rid):
            return node
    return None


def _find_first_search_result(nodes: list, app_name: str, search_y: int) -> Any | None:
    """Pick the first app row inside the launcher 'Searched Apps' section."""
    by_id = _nodes_by_id(nodes)
    query = app_name.lower()

    container = _find_searched_apps_container(nodes)
    if container is not None:
        result = _first_app_in_subtree(container, by_id)
        if result is not None:
            return result

    header = next((n for n in nodes if _is_searched_apps_header(n)), None)
    if header is not None:
        section_top = header.bounds["y"] + header.bounds["h"]
        section_bottom = section_top + 900
        section_candidates = [
            n
            for n in nodes
            if _is_launcher_app_result(n)
            and section_top <= n.bounds["y"] < section_bottom
        ]
        if section_candidates:
            section_candidates.sort(key=lambda n: (n.bounds["y"], n.bounds["x"]))
            return section_candidates[0]

    # Last resort: first labeled match below the search field (legacy behaviour).
    text_candidates = []
    for node in nodes:
        if not _is_launcher_app_result(node):
            continue
        label = (node.text or node.content_desc or "").strip().lower()
        if node.center["y"] <= search_y + 20:
            continue
        if query in label or label.startswith(query):
            text_candidates.append(node)
    if text_candidates:
        text_candidates.sort(key=lambda n: (n.bounds["y"], n.bounds["x"]))
        return text_candidates[0]

    return None


def _find_search_field(nodes: list) -> Any | None:
    for node in nodes:
        label = f"{node.text} {node.content_desc}".lower()
        rid = node.resource_id.lower()
        if "search" in label or "search" in rid:
            if node.clickable or node.focusable or "EditText" in node.cls:
                return node
    for node in nodes:
        if "EditText" in node.cls and (node.clickable or node.focusable):
            return node
    return None


_SETTINGS_SELECTORS: list[dict[str, str]] = [
    {"text": "Settings"},
    {"text": "Einstellungen"},
    {"content_desc": "Settings"},
    {"content_desc": "Einstellungen"},
    {"text_contains": "Settings"},
    {"text_contains": "Einstellungen"},
]

_MENU_SELECTORS: list[dict[str, str]] = [
    {"content_desc": "More options"},
    {"content_desc": "Weitere Optionen"},
    {"content_desc": "Menu"},
    {"text": "Menu"},
    {"text_contains": "View more"},
    {"text_contains": "Mehr anzeigen"},
    {"text_contains": "Mehr"},
]


def _find_by_selectors(nodes: list, selectors: list[dict[str, str]]) -> Any | None:
    for sel in selectors:
        best: tuple[int, Any] | None = None
        for node in nodes:
            if not (node.clickable or node.long_clickable):
                continue
            score = _score_node(node, sel)
            if score > 0 and (best is None or score > best[0]):
                best = (score, node)
        if best is not None:
            return best[1]
    return None


def _find_overflow_menu(nodes: list) -> Any | None:
    found = _find_by_selectors(nodes, _MENU_SELECTORS)
    if found is not None:
        return found
    for node in nodes:
        if not (node.clickable or node.long_clickable):
            continue
        label = f"{node.text} {node.content_desc}".lower()
        if any(token in label for token in ("more option", "overflow", " view more", "weitere option")):
            return node
    return None


def _tap_node(serial: str, node: Any) -> dict[str, Any]:
    from .input import _tap

    selector: dict[str, str] = {}
    if node.text:
        selector["text"] = node.text
    elif node.content_desc:
        selector["content_desc"] = node.content_desc
    elif node.resource_id:
        selector["resource_id"] = node.resource_id
    else:
        selector["id"] = node.id
    return _tap(selector=selector, device_serial=serial)


@tool_safe
def _navigate_in_app_settings(device_serial: str | None = None) -> dict[str, Any]:
    """
    Open in-app Settings with fallback: Settings button → overflow/menu → Settings.
    Use after launch_app when the app is already open.
    """
    serial = _serial(device_serial)

    # Allow the launched app UI to finish opening before we read the tree.
    time.sleep(cfg.app_ui_settle_ms / 1000)

    nodes = _capture_nodes(serial)
    settings = _find_by_selectors(nodes, _SETTINGS_SELECTORS)
    if settings is not None:
        tap_result = _tap_node(serial, settings)
        return {
            "ok": True,
            "path": "direct",
            "tapped": settings.text or settings.content_desc or settings.resource_id,
            "tap": tap_result,
        }

    menu = _find_overflow_menu(nodes)
    if menu is None:
        raise AgentError(
            ErrorCode.SELECTOR_NO_MATCH,
            "Neither Settings nor Menu/View-more control found on the current screen.",
            hint="Call get_screen(mode='text') to inspect visible controls, then retry after navigation.",
        )

    menu_tap = _tap_node(serial, menu)
    time.sleep(0.8)
    nodes = _capture_nodes(serial)
    settings = _find_by_selectors(nodes, _SETTINGS_SELECTORS)
    if settings is None:
        raise AgentError(
            ErrorCode.SELECTOR_NO_MATCH,
            "Opened menu/overflow but Settings was not found in the opened panel.",
            hint="Call get_screen after opening the menu and tap Settings by id or text.",
            extra={"menu_tapped": menu.text or menu.content_desc},
        )

    settings_tap = _tap_node(serial, settings)
    return {
        "ok": True,
        "path": "via_menu",
        "menu_tapped": menu.text or menu.content_desc or menu.resource_id,
        "settings_tapped": settings.text or settings.content_desc or settings.resource_id,
        "menu_tap": menu_tap,
        "settings_tap": settings_tap,
    }


def _launch_via_launcher_search(
    serial: str,
    app_name: str,
    adb_dev,
) -> dict[str, Any]:
    """Open the app drawer search, type app_name, tap the first matching result."""
    from .input import _type_text

    d = device_manager.resolve_u2(serial)
    d.press("home")
    time.sleep(0.6)

    w, h = d.window_size()
    d.swipe(w // 2, h * 3 // 4, w // 2, h // 4, duration=0.35)
    time.sleep(0.9)

    nodes = _capture_nodes(serial)
    search = _find_search_field(nodes)
    if search is None:
        raise AgentError(
            ErrorCode.SELECTOR_NO_MATCH,
            "Could not find launcher search field for app search fallback.",
            hint="Ensure the home/app drawer is visible, or pass package+activity directly.",
        )

    d.click(search.center["x"], search.center["y"])
    time.sleep(0.4)
    _type_text(text=app_name, clear=True, device_serial=serial)
    time.sleep(1.5)

    nodes = _capture_nodes(serial, max_nodes=120)
    result = _find_first_search_result(nodes, app_name, search.center["y"])
    if result is None:
        raise AgentError(
            ErrorCode.SELECTOR_NO_MATCH,
            f"No launcher search result found for {app_name!r}.",
            hint="Check spelling or try a shorter app_name.",
            extra={"app_name": app_name},
        )

    d.click(result.center["x"], result.center["y"])
    time.sleep(0.3)
    d.press("enter")
    snapshot_cache.invalidate(serial)

    needles = _foreground_needles(app_name, label=result.text or result.content_desc or "")
    foreground = _wait_for_foreground(adb_dev, *needles)
    if not foreground:
        # Some launchers need a second tap on the search row to open the app.
        d.click(result.center["x"], result.center["y"])
        snapshot_cache.invalidate(serial)
        foreground = _wait_for_foreground(adb_dev, *needles)
    return {
        "launch_method": "search",
        "app_name": app_name,
        "matched_label": result.text or result.content_desc,
        "matched_package": result.package,
        "foreground": foreground,
    }


@tool_safe
def _launch_app(
    package: str | None = None,
    activity: str | None = None,
    uri: str | None = None,
    app_name: str | None = None,
    wait: bool = True,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)
    launch_method = "package"
    search_meta: dict[str, Any] = {}

    if uri:
        cmd = f"am start -a android.intent.action.VIEW -d {uri}"
        if package:
            cmd += f" -n {package}"
        out = adb_dev.shell(cmd)
    elif package or activity:
        if package and activity:
            out = adb_dev.shell(f"am start -n {package}/{activity}")
        elif package:
            out = adb_dev.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
        else:
            raise AgentError(
                ErrorCode.INVALID_ARGUMENT,
                "activity requires package.",
            )

        if "Error" in str(out) and "java.lang" in str(out):
            raise AgentError(ErrorCode.ADB_COMMAND_FAILED, str(out), hint="Check package name or intent URI.")
    elif app_name:
        search_meta = _launch_via_launcher_search(serial, app_name, adb_dev)
        return {
            "ok": True,
            "package": search_meta.get("matched_package") or app_name,
            "activity_resolved": "",
            "foreground": search_meta.get("foreground", False),
            "launch_method": "search",
            "app_name": app_name,
            "matched_label": search_meta.get("matched_label"),
        }
    else:
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            "Provide package, package+activity, uri, or app_name.",
        )

    foreground = False
    if wait:
        name_hint = app_name or (package and _derive_app_name(package)) or ""
        needles = _foreground_needles(name_hint, package=package or "")
        foreground = _wait_for_foreground(adb_dev, *needles)

        search_label = name_hint
        if not foreground and search_label:
            log.info("Package launch did not reach foreground; trying launcher search for %r", search_label)
            try:
                search_meta = _launch_via_launcher_search(serial, search_label, adb_dev)
                launch_method = "search"
                foreground = search_meta.get("foreground", False)
            except AgentError as exc:
                log.warning("Launcher search fallback failed: %s", exc)
                return {
                    "ok": True,
                    "package": package or uri,
                    "activity_resolved": activity or "",
                    "foreground": False,
                    "launch_method": launch_method,
                    "search_fallback": {"attempted": True, "ok": False, "message": str(exc), "hint": exc.hint},
                }

    resolved_activity = activity or ""
    if not resolved_activity and package:
        try:
            dump = adb_dev.shell(f"pm dump {package} | grep -m1 MAIN")
            m = re.search(r"(\S+/\S+)", dump)
            if m:
                resolved_activity = m.group(1)
        except Exception:
            pass

    result: dict[str, Any] = {
        "ok": True,
        "package": package or uri,
        "activity_resolved": resolved_activity,
        "foreground": foreground,
        "launch_method": launch_method,
    }
    if search_meta:
        result["search_fallback"] = {
            "attempted": True,
            "ok": foreground,
            "app_name": search_meta.get("app_name"),
            "matched_label": search_meta.get("matched_label"),
            "matched_package": search_meta.get("matched_package"),
        }
    return result


@tool_safe
def _list_packages(
    filter: str = "user",
    name_contains: str | None = None,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    flag = {
        "user": "-3",
        "system": "-s",
        "all": "",
    }.get(filter, "-3")

    raw = adb_dev.shell(f"pm list packages {flag}")
    packages = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        pkg = line[len("package:"):]
        if name_contains and name_contains.lower() not in pkg.lower():
            continue
        packages.append(pkg)

    # Get version info in batch (one dumpsys is too slow; parse `pm list packages -v` instead)
    raw_v = adb_dev.shell(f"pm list packages {flag} -v")
    version_map: dict[str, str] = {}
    for line in raw_v.strip().splitlines():
        m = re.match(r"package:(\S+)\s+versionCode:(\S+)", line)
        if m:
            version_map[m.group(1)] = m.group(2)

    result = []
    for pkg in packages:
        result.append({"package": pkg, "enabled": True, "version": version_map.get(pkg, "")})

    return {"ok": True, "packages": result, "total": len(result)}


@tool_safe
def _app_info(
    package: str,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    dump = adb_dev.shell(f"dumpsys package {package}")

    # Version
    version = ""
    m = re.search(r"versionName=(\S+)", dump)
    if m:
        version = m.group(1)

    # Main activity
    main_activity = ""
    m = re.search(r"android\.intent\.action\.MAIN.*?(\S+/\S+)", dump, re.DOTALL)
    if not m:
        m = re.search(r"(\S+/\S+Activity)", dump)
    if m:
        main_activity = m.group(1)

    # Permissions
    granted: list[str] = []
    requested: list[str] = []

    in_requested = False
    for line in dump.splitlines():
        ls = line.strip()
        if "granted=true" in ls:
            pm = re.search(r"(android\.permission\.\w+)", ls)
            if pm:
                granted.append(pm.group(1))
        elif "declared permissions" in ls.lower():
            in_requested = True
        elif in_requested:
            pm = re.search(r"(android\.permission\.\w+)", ls)
            if pm:
                requested.append(pm.group(1))
            elif ls.startswith("Package") or not ls:
                in_requested = False

    # Foreground status
    focus = adb_dev.shell("dumpsys window windows | grep mCurrentFocus")
    is_foreground = package in focus

    return {
        "ok": True,
        "app": {
            "package": package,
            "version": version,
            "main_activity": main_activity,
            "permissions": {
                "granted": list(set(granted)),
                "requested": list(set(requested)),
            },
            "is_foreground": is_foreground,
        },
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(
        name="launch_app",
        description=(
            "Launch an app by package name, package+activity, deep-link URI, or app_name. "
            "Examples: launch_app(package='com.android.settings'), "
            "launch_app(app_name='Bixby'). "
            "When a package launch does not reach the foreground, automatically falls back to "
            "opening the launcher search, typing app_name, and tapping the first matching result. "
            "Returns foreground:true when the app is confirmed in focus after launch."
        ),
    )(_launch_app)

    mcp.tool(
        name="list_packages",
        description=(
            "List installed packages. filter='user' (default) shows user-installed apps only, "
            "'system' shows system apps, 'all' shows everything. "
            "Use name_contains to search by substring."
        ),
    )(_list_packages)

    mcp.tool(
        name="app_info",
        description=(
            "Get detailed info for one app: version, main activity, "
            "granted/requested permissions, and whether it is currently in the foreground. "
            "Useful before navigating into an app's settings."
        ),
    )(_app_info)

    mcp.tool(
        name="navigate_in_app_settings",
        description=(
            "Navigate to Settings inside the currently open app. "
            "First tries to tap Settings/Einstellungen directly. "
            "If not visible, taps Menu, More options, or View more, then Settings. "
            "Use after launch_app(app_name='...') when you need the app's own settings screen."
        ),
    )(_navigate_in_app_settings)
