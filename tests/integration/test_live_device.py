"""
Integration tests — require a physical Android device connected via ADB.

Run with:
    pytest tests/integration/ -v

These tests are skipped automatically if no ADB device is detected.
"""
from __future__ import annotations

import pytest


def _has_device() -> bool:
    try:
        import adbutils
        client = adbutils.AdbClient(host="127.0.0.1", port=5037)
        return len(client.device_list()) > 0
    except Exception:
        return False


skip_no_device = pytest.mark.skipif(not _has_device(), reason="No ADB device connected")


@skip_no_device
def test_list_devices():
    from adb_mcp.tools.diag import _list_devices
    result = _list_devices()
    assert result["ok"] is True
    assert len(result["devices"]) >= 1
    assert result["devices"][0]["serial"]


@skip_no_device
def test_device_info():
    from adb_mcp.tools.diag import _device_info
    result = _device_info()
    assert result["ok"] is True
    info = result["info"]
    assert info["sdk_int"]
    assert info["screen"]["w"] > 0
    assert info["screen"]["h"] > 0


@skip_no_device
def test_launch_settings_app():
    from adb_mcp.tools.apps import _launch_app
    result = _launch_app(package="com.android.settings", wait=True)
    assert result["ok"] is True


@skip_no_device
def test_get_screen_text_mode():
    from adb_mcp.tools.screen import _get_screen
    result = _get_screen(mode="text", include_ocr=False)
    assert result["ok"] is True
    assert len(result["tree"]) >= 5
    assert "image_b64" not in result


@skip_no_device
def test_get_screen_vision_mode():
    from adb_mcp.tools.screen import _get_screen
    result = _get_screen(mode="vision")
    assert result["ok"] is True
    assert "image_b64" in result
    assert result["image_mime"] == "image/png"


@skip_no_device
def test_get_screen_snapshot_id_stable():
    from adb_mcp.tools.screen import _get_screen
    r1 = _get_screen(mode="text", include_ocr=False)
    r2 = _get_screen(mode="text", include_ocr=False)
    # snapshot_id should change since we capture fresh each time
    assert r1["snapshot_id"] != r2["snapshot_id"]


@skip_no_device
def test_tap_by_text():
    """Navigate to Network settings and tap an element by text selector."""
    import time

    from adb_mcp.tools.apps import _launch_app
    from adb_mcp.tools.input import _tap
    from adb_mcp.tools.screen import _get_screen

    _launch_app(package="com.android.settings", wait=True)
    time.sleep(1)

    screen = _get_screen(mode="text", include_ocr=False)
    assert screen["ok"]

    # Find any clickable element with text and tap it
    tree = screen["tree"]
    target = next(
        (n for n in tree if n.get("clickable") and n.get("text") and "network" in n["text"].lower()),
        None,
    )
    if target is None:
        # Just tap the first clickable element
        target = next((n for n in tree if n.get("clickable") and n.get("text")), None)

    if target:
        result = _tap(selector={"text": target["text"]})
        assert result["ok"] is True


@skip_no_device
def test_open_settings_wifi():
    from adb_mcp.tools.settings import _open_settings
    result = _open_settings(panel="wifi")
    assert result["ok"] is True
    assert "wifi" in result["intent_used"].lower()


@skip_no_device
def test_wait_for_appears():
    from adb_mcp.tools.screen import _wait_for
    from adb_mcp.tools.settings import _open_settings

    _open_settings(panel="wifi")
    result = _wait_for(selector={"text_contains": "Wi"}, condition="appear", timeout_ms=6000)
    assert result["ok"] is True
    assert result["matched"] is True


@skip_no_device
def test_get_logcat():
    from adb_mcp.tools.diag import _get_logcat
    result = _get_logcat(tag_filter="ActivityManager", max_lines=20)
    assert result["ok"] is True
    assert isinstance(result["lines"], list)


@skip_no_device
def test_press_key_home():
    from adb_mcp.tools.input import _press_key
    result = _press_key(key="home")
    assert result["ok"] is True


@skip_no_device
def test_grant_permission_camera():
    """
    Attempts to grant CAMERA permission to Settings (which doesn't need it,
    but the command should succeed or return a known error — not crash).
    """
    from adb_mcp.tools.settings import _grant_permission
    result = _grant_permission(
        package="com.android.settings",
        permission="android.permission.CAMERA",
        action="grant",
    )
    # Either ok or a known ADB error is fine — we just want no crash.
    assert "ok" in result
