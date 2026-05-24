from __future__ import annotations

import logging
import os

import adbutils
import uiautomator2 as u2

from .config import cfg
from .errors import AgentError, ErrorCode

log = logging.getLogger(__name__)

# Set adbutils to use the configured adb binary.
os.environ.setdefault("ADBUTILS_ADB_PATH", cfg.adb_path)


class DeviceManager:
    """Resolves device serials and caches uiautomator2 connections."""

    def __init__(self) -> None:
        self._adb = adbutils.AdbClient(host="127.0.0.1", port=5037)
        self._u2_cache: dict[str, u2.Device] = {}

    # ------------------------------------------------------------------
    # ADB device
    # ------------------------------------------------------------------

    def list_adb_devices(self) -> list[adbutils.AdbDevice]:
        return self._adb.device_list()

    def resolve_adb(self, serial: str | None = None) -> adbutils.AdbDevice:
        devices = self.list_adb_devices()
        online = [d for d in devices if d.info.get("status") == "device" or True]
        # filter to only 'device' state
        online = [d for d in devices]

        if not online:
            raise AgentError(
                ErrorCode.DEVICE_NOT_FOUND,
                "No ADB devices found.",
                hint="Connect a device and enable USB debugging, then retry.",
            )

        if serial:
            for d in online:
                if d.serial == serial:
                    return d
            raise AgentError(
                ErrorCode.DEVICE_NOT_FOUND,
                f"Device {serial!r} not found.",
                hint=f"Available: {[d.serial for d in online]}",
            )

        if len(online) == 1:
            return online[0]

        if cfg.default_device:
            for d in online:
                if d.serial == cfg.default_device:
                    return d

        raise AgentError(
            ErrorCode.MULTIPLE_DEVICES,
            "Multiple devices connected and no serial specified.",
            hint="Pass device_serial or set default_device in config.yaml.",
            extra={"devices": [d.serial for d in online]},
        )

    # ------------------------------------------------------------------
    # uiautomator2 connection (cached per serial)
    # ------------------------------------------------------------------

    def resolve_u2(self, serial: str | None = None) -> u2.Device:
        adb_device = self.resolve_adb(serial)
        s = adb_device.serial
        if s not in self._u2_cache:
            log.debug("Connecting uiautomator2 to %s", s)
            self._u2_cache[s] = u2.connect(s)
        return self._u2_cache[s]

    def invalidate_u2(self, serial: str) -> None:
        self._u2_cache.pop(serial, None)


# Module-level singleton.
device_manager = DeviceManager()
