from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ToolTimeouts(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    default: int = 10_000
    wait_for: int = 15_000
    launch_app: int = 12_000


class Config(BaseSettings):
    """Runtime configuration. Values can be overridden with ADB_MCP_* env vars."""

    model_config = SettingsConfigDict(
        env_prefix="ADB_MCP_",
        extra="ignore",
    )

    adb_path: str = "adb"
    default_device: str | None = None
    ocr_enabled: bool = True
    ocr_engine: str = "paddle"          # paddle | tesseract | none
    screenshot_max_dim: int = 1280
    som_default_enabled: bool = True
    destructive_ops_enabled: bool = False
    logcat_max_lines: int = 500
    hierarchy_cache_ms: int = 1500
    tool_timeouts_ms: ToolTimeouts = ToolTimeouts()
    log_level: str = "INFO"

    @field_validator("ocr_engine")
    @classmethod
    def _valid_engine(cls, v: str) -> str:
        allowed = {"paddle", "tesseract", "none"}
        if v not in allowed:
            raise ValueError(f"ocr_engine must be one of {allowed}")
        return v


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_config() -> Config:
    cfg_path_env = os.environ.get("ADB_MCP_CONFIG")
    if cfg_path_env:
        cfg_path = Path(cfg_path_env)
    else:
        cfg_path = Path.cwd() / "config.yaml"

    raw = _load_yaml(cfg_path)

    # Flatten nested tool_timeouts_ms for pydantic-settings
    if "tool_timeouts_ms" in raw and isinstance(raw["tool_timeouts_ms"], dict):
        raw["tool_timeouts_ms"] = ToolTimeouts(**raw["tool_timeouts_ms"])

    return Config(**raw)


# Module-level singleton — imported everywhere.
cfg = load_config()
