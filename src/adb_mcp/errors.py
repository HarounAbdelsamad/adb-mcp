from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    SELECTOR_NO_MATCH = "SELECTOR_NO_MATCH"
    SELECTOR_AMBIGUOUS = "SELECTOR_AMBIGUOUS"
    HIERARCHY_STALE = "HIERARCHY_STALE"
    ADB_COMMAND_FAILED = "ADB_COMMAND_FAILED"
    UIAUTOMATOR_NOT_READY = "UIAUTOMATOR_NOT_READY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DESTRUCTIVE_OP_DISABLED = "DESTRUCTIVE_OP_DISABLED"
    TIMEOUT = "TIMEOUT"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNKNOWN = "UNKNOWN"


class AgentError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        hint: str = "",
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.extra = extra or {}

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ok": False,
            "error_code": self.code.value,
            "message": str(self),
        }
        if self.hint:
            d["hint"] = self.hint
        d.update(self.extra)
        return d


def tool_safe(func: Callable) -> Callable:
    """Wrap a tool function so exceptions become structured {ok:false,...} dicts."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except AgentError as exc:
            log.debug("AgentError in %s: %s", func.__name__, exc)
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error in tool %s", func.__name__)
            return {
                "ok": False,
                "error_code": ErrorCode.UNKNOWN.value,
                "message": str(exc),
                "hint": "Check ADB connection and device status. Run list_devices to verify.",
            }

    return wrapper
