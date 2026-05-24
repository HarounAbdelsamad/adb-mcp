from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..config import cfg
from ..device import device_manager
from ..errors import AgentError, ErrorCode, tool_safe

log = logging.getLogger(__name__)

# Map short panel names → Android Settings intents
# Include the ~20 most useful panels for onboarding/settings flows.
_SETTINGS_PANELS: dict[str, str] = {
    "home": "android.settings.SETTINGS",
    "wifi": "android.settings.WIFI_SETTINGS",
    "bluetooth": "android.settings.BLUETOOTH_SETTINGS",
    "data_usage": "android.settings.DATA_USAGE_SETTINGS",
    "mobile_data": "android.settings.DATA_ROAMING_SETTINGS",
    "airplane_mode": "android.settings.AIRPLANE_MODE_SETTINGS",
    "network": "android.settings.WIRELESS_SETTINGS",
    "display": "android.settings.DISPLAY_SETTINGS",
    "sound": "android.settings.SOUND_SETTINGS",
    "notifications": "android.settings.NOTIFICATION_SETTINGS",
    "apps": "android.settings.APPLICATION_SETTINGS",
    "app_details": "android.settings.APPLICATION_DETAILS_SETTINGS",
    "default_apps": "android.settings.MANAGE_DEFAULT_APPS_SETTINGS",
    "accessibility": "android.settings.ACCESSIBILITY_SETTINGS",
    "language": "android.settings.LOCALE_SETTINGS",
    "date_time": "android.settings.DATE_SETTINGS",
    "location": "android.settings.LOCATION_SOURCE_SETTINGS",
    "security": "android.settings.SECURITY_SETTINGS",
    "privacy": "android.settings.PRIVACY_SETTINGS",
    "battery": "android.settings.BATTERY_SAVER_SETTINGS",
    "storage": "android.settings.INTERNAL_STORAGE_SETTINGS",
    "developer": "android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
    "accounts": "android.settings.SYNC_SETTINGS",
    "about": "android.settings.DEVICE_INFO_SETTINGS",
    "nfc": "android.settings.NFC_SETTINGS",
    "hotspot": "android.settings.TETHER_PROVISIONING_UI",
}


def _serial(device_serial: str | None) -> str:
    return device_manager.resolve_adb(device_serial).serial


@tool_safe
def _open_settings(
    panel: str,
    package: str | None = None,
    device_serial: str | None = None,
) -> dict[str, Any]:
    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    panel_key = panel.lower().replace("-", "_").replace(" ", "_")
    intent = _SETTINGS_PANELS.get(panel_key)

    if intent is None:
        available = list(_SETTINGS_PANELS.keys())
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            f"Unknown settings panel: {panel!r}.",
            hint=f"Available panels: {available}",
        )

    if panel_key == "app_details" and package:
        cmd = f"am start -a {intent} -d package:{package}"
    else:
        cmd = f"am start -a {intent}"

    out = adb_dev.shell(cmd)

    if "Error" in str(out) and "java.lang" in str(out):
        raise AgentError(ErrorCode.ADB_COMMAND_FAILED, str(out))

    return {"ok": True, "panel": panel, "intent_used": intent}


@tool_safe
def _grant_permission(
    package: str,
    permission: str,
    action: str = "grant",
    device_serial: str | None = None,
) -> dict[str, Any]:
    if action == "revoke" and not cfg.destructive_ops_enabled:
        raise AgentError(
            ErrorCode.DESTRUCTIVE_OP_DISABLED,
            "Revoking permissions is a destructive operation and is disabled by default.",
            hint="Set destructive_ops_enabled: true in config.yaml to enable it.",
        )

    if action not in ("grant", "revoke"):
        raise AgentError(
            ErrorCode.INVALID_ARGUMENT,
            "action must be 'grant' or 'revoke'.",
        )

    serial = _serial(device_serial)
    adb_dev = device_manager.resolve_adb(serial)

    cmd = f"pm {action} {package} {permission}"
    out = adb_dev.shell(cmd)

    if out and ("Exception" in out or "Unknown" in out):
        raise AgentError(
            ErrorCode.ADB_COMMAND_FAILED,
            out.strip(),
            hint="Check that the package name and permission string are correct.",
        )

    return {"ok": True, "package": package, "permission": permission, "action": action}


def register(mcp: FastMCP) -> None:
    available_panels = list(_SETTINGS_PANELS.keys())
    mcp.tool(
        name="open_settings",
        description=(
            "Deep-link directly into a specific Android settings panel — faster than navigating manually. "
            f"Available panels: {available_panels}. "
            "For app_details, also pass the package parameter. "
            "Ideal starting point for onboarding and settings configuration flows."
        ),
    )(_open_settings)

    mcp.tool(
        name="grant_permission",
        description=(
            "Grant (or revoke) a runtime permission for an app via ADB. "
            "Example: grant_permission(package='com.example.app', permission='android.permission.CAMERA'). "
            "Revoke requires destructive_ops_enabled=true in config. "
            "Common in app onboarding flows that require location, camera, or contacts access."
        ),
    )(_grant_permission)
