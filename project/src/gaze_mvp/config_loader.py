from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class LlmConfig:
    provider: str
    api_style: str
    base_url: str
    model: str
    api_key_env: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int


@dataclass
class AppConfig:
    openface_bin: Path
    model_loc: Path
    default_out_dir: Path
    dwell_ms: int
    llm: LlmConfig


def _expect_object(obj: Any, context: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{context} must be an object.")
    return obj


def _as_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _as_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    return value


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{field_name} must be a number.")


def load_app_config(path: Path) -> AppConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    root = _expect_object(raw, "config")

    llm_raw = _expect_object(root.get("llm"), "config.llm")
    llm = LlmConfig(
        provider=_as_str(llm_raw.get("provider"), "config.llm.provider"),
        api_style=_as_str(llm_raw.get("api_style"), "config.llm.api_style"),
        base_url=_as_str(llm_raw.get("base_url"), "config.llm.base_url").rstrip("/"),
        model=_as_str(llm_raw.get("model"), "config.llm.model"),
        api_key_env=_as_str(llm_raw.get("api_key_env"), "config.llm.api_key_env"),
        temperature=_as_float(llm_raw.get("temperature"), "config.llm.temperature"),
        max_output_tokens=_as_int(llm_raw.get("max_output_tokens"), "config.llm.max_output_tokens"),
        timeout_seconds=_as_int(llm_raw.get("timeout_seconds", 30), "config.llm.timeout_seconds"),
    )

    return AppConfig(
        openface_bin=Path(_as_str(root.get("openface_bin"), "config.openface_bin")),
        model_loc=Path(_as_str(root.get("model_loc"), "config.model_loc")),
        default_out_dir=Path(_as_str(root.get("default_out_dir"), "config.default_out_dir")),
        dwell_ms=_as_int(root.get("dwell_ms"), "config.dwell_ms"),
        llm=llm,
    )
