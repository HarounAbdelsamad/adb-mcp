from __future__ import annotations

import logging
import re
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..device import device_manager
from ..errors import AgentError, ErrorCode, tool_safe

log = logging.getLogger(__name__)


def _serial(device_serial: str | None) -> str:
    return device_manager.resolve_adb(device_serial).serial


@tool_safe
def _launch_app(
    package: str | None = None,
    activity: str | None = None,
    uri: str | None = None,
    wait: bool = True,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    if uri:
        cmd = f"am start -a android.intent.action.VIEW -d {uri}"
        if package:
            cmd += f" -n {package}"
        out = adb_dev.shell(cmd)
    elif package and activity:
        out = adb_dev.shell(f"am start -n {package}/{activity}")
    elif package:
        # Use monkey to launch default activity
        out = adb_dev.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
    else:
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            "Provide package, package+activity, or uri.",
        )

    if "Error" in str(out) and "java.lang" in str(out):
        raise AgentError(ErrorCode.ADB_COMMAND_FAILED, str(out), hint="Check package name or intent URI.")

    # Resolve actual foreground activity
    foreground = False
    if wait and package:
        time.sleep(1.0)
        focus = adb_dev.shell("dumpsys window windows | grep mCurrentFocus")
        foreground = package in focus

    resolved_activity = activity or ""
    if not resolved_activity and package:
        try:
            dump = adb_dev.shell(f"pm dump {package} | grep -m1 MAIN")
            m = re.search(r"(\S+/\S+)", dump)
            if m:
                resolved_activity = m.group(1)
        except Exception:
            pass

    return {
        "ok": True,
        "package": package or uri,
        "activity_resolved": resolved_activity,
        "foreground": foreground,
    }


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
            "Launch an app by package name, package+activity, or deep-link URI. "
            "Examples: launch_app(package='com.android.settings'), "
            "launch_app(uri='content://contacts'). "
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
