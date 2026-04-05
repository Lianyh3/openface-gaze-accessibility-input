from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class OpenFaceCsvConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    csv_path: Path
    poll_interval_ms: int = Field(default=40, ge=5, le=1000)
    has_header: bool = True
    timestamp_column: str = "timestamp"
    confidence_column: str = "confidence"
    frame_column: str = "frame"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = "dev-session"
    log_dir: Path = Path("logs")


class AiConfig(BaseModel):
    enabled: bool = False
    model: str = "gpt-5.3-codex"
    timeout_ms: int = Field(default=1000, ge=100, le=10000)
    top_k: int = Field(default=5, ge=1, le=10)
    min_prefix_chars: int = Field(default=2, ge=1, le=20)
    endpoint: str = "https://api.openai.com/v1/responses"
    api_key_env: str = "OPENAI_API_KEY"
