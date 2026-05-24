from __future__ import annotations

import logging
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..device import device_manager
from ..errors import AgentError, ErrorCode, tool_safe

log = logging.getLogger(__name__)

_DUMPSYS_PARSERS: dict[str, Any] = {}


def _parse_battery(raw: str) -> dict:
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        m = re.match(r"\s+(\w[\w ]+):\s+(.+)", line)
        if m:
            result[m.group(1).strip().replace(" ", "_")] = m.group(2).strip()
    return result


def _parse_window(raw: str) -> dict:
    lines = raw.splitlines()
    focus = ""
    for line in lines:
        if "mCurrentFocus" in line or "mFocusedWindow" in line:
            focus = line.strip()
            break
    return {"current_focus": focus}


def _parse_activity(raw: str) -> dict:
    resumed = ""
    for line in raw.splitlines():
        if "mResumedActivity" in line:
            resumed = line.strip()
            break
    return {"resumed_activity": resumed}


_SERVICE_PARSERS = {
    "battery": _parse_battery,
    "window": _parse_window,
    "activity": _parse_activity,
}


def _serial(device_serial: str | None) -> str:
    return device_manager.resolve_adb(device_serial).serial


@tool_safe
def _list_devices() -> dict[str, Any]:
    devices = device_manager.list_adb_devices()
    result = []
    for d in devices:
        info = d.info
        serial = d.serial
        try:
            android_ver = d.prop.get("ro.build.version.release", "")
            model = d.prop.get("ro.product.model", "")
        except Exception:
            android_ver = ""
            model = ""
        result.append({
            "serial": serial,
            "state": info.get("status", "unknown"),
            "model": model,
            "android_version": android_ver,
        })
    return {"ok": True, "devices": result}


@tool_safe
def _device_info(device_serial: str | None = None) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    def prop(key: str) -> str:
        try:
            return adb_dev.prop.get(key, "")
        except Exception:
            return ""

    # Screen size
    wm = adb_dev.shell("wm size")
    screen = {"w": 0, "h": 0}
    m = re.search(r"(\d+)x(\d+)", wm)
    if m:
        screen = {"w": int(m.group(1)), "h": int(m.group(2))}

    # Screen density
    density_raw = adb_dev.shell("wm density")
    density = 0
    dm = re.search(r"(\d+)", density_raw)
    if dm:
        density = int(dm.group(1))

    # Battery
    bat_raw = adb_dev.shell("dumpsys battery | grep level")
    bat_level = ""
    bm = re.search(r"level: (\d+)", bat_raw)
    if bm:
        bat_level = bm.group(1) + "%"

    # Network interfaces (just list IP)
    net_raw = adb_dev.shell("ip addr show wlan0 | grep 'inet '")
    ip = ""
    nm = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", net_raw)
    if nm:
        ip = nm.group(1)

    return {
        "ok": True,
        "info": {
            "serial": serial,
            "model": prop("ro.product.model"),
            "manufacturer": prop("ro.product.manufacturer"),
            "android_version": prop("ro.build.version.release"),
            "sdk_int": prop("ro.build.version.sdk"),
            "build_id": prop("ro.build.id"),
            "screen": screen,
            "density_dpi": density,
            "battery": bat_level,
            "wifi_ip": ip,
        },
    }


@tool_safe
def _get_logcat(
    tag_filter: str | None = None,
    priority: str = "W",
    max_lines: int = 200,
    since_ms: int | None = None,
    clear_first: bool = False,
    device_serial: str | None = None,
) -> dict[str, Any]:
    from ..config import cfg
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    cap = min(max_lines, cfg.logcat_max_lines)

    if clear_first:
        adb_dev.shell("logcat -c")

    filter_spec = f"{tag_filter}:{priority}" if tag_filter else f"*:{priority}"
    cmd = f"logcat -d -t {cap} -v brief {filter_spec}"
    raw = adb_dev.shell(cmd)

    lines = []
    # logcat brief format: I/TAG(PID): message
    pattern = re.compile(r"^([A-Z])/(.*?)\(\s*(\d+)\):\s(.*)$")
    for line in raw.strip().splitlines():
        m = pattern.match(line)
        if m:
            lines.append({
                "prio": m.group(1),
                "tag": m.group(2).strip(),
                "pid": m.group(3),
                "msg": m.group(4),
                "ts": "",
            })
        else:
            lines.append({"prio": "", "tag": "", "pid": "", "msg": line, "ts": ""})

    truncated = len(lines) >= cap
    return {"ok": True, "lines": lines, "truncated": truncated, "total": len(lines)}


@tool_safe
def _dumpsys_query(
    service: str,
    query: str | None = None,
    raw: bool = False,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    safe_services = {
        "window", "activity", "battery", "power", "package",
        "notification", "meminfo", "cpuinfo", "display",
        "alarm", "connectivity", "wifi", "telephony.registry",
        "statusbar", "input_method",
    }
    if service not in safe_services:
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            f"Service {service!r} is not in the allowed list.",
            hint=f"Allowed services: {sorted(safe_services)}",
        )

    cmd = f"dumpsys {service}"
    if query:
        cmd += f" | grep -i {query}"
    raw_text = adb_dev.shell(cmd)

    parsed = {}
    parser = _SERVICE_PARSERS.get(service)
    if parser:
        try:
            parsed = parser(raw_text)
        except Exception:
            pass

    result: dict[str, Any] = {"ok": True, "service": service, "parsed": parsed}
    if raw:
        result["raw_text"] = raw_text[:4000]  # cap at 4 KB
    return result


def register(mcp: FastMCP) -> None:
    mcp.tool(
        name="list_devices",
        description=(
            "List all ADB-connected devices with serial, state, model, and Android version. "
            "Always call this first to confirm a device is connected and get the serial for multi-device setups."
        ),
    )(_list_devices)

    mcp.tool(
        name="device_info",
        description=(
            "Get detailed device info: model, manufacturer, Android version, SDK level, "
            "screen resolution, DPI, battery level, and Wi-Fi IP. "
            "Useful for adapting automation to the device's screen size."
        ),
    )(_device_info)

    mcp.tool(
        name="get_logcat",
        description=(
            "Read recent Android logs. "
            "Use tag_filter to narrow to a specific component (e.g. 'ActivityManager', 'WifiManager'). "
            "priority: V=verbose, D=debug, I=info, W=warn (default), E=error. "
            "Returns parsed lines with priority, tag, pid, and message."
        ),
    )(_get_logcat)

    mcp.tool(
        name="dumpsys_query",
        description=(
            "Query an Android system service via dumpsys. "
            "Allowed services: window, activity, battery, power, package, notification, "
            "meminfo, cpuinfo, display, alarm, connectivity, wifi, telephony.registry, statusbar, input_method. "
            "Use parsed output for common services; set raw=true to get full text."
        ),
    )(_dumpsys_query)
