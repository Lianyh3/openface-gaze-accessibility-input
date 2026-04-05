from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence


DwellState = Literal["enter", "stay", "fire", "cancel"]
ActionType = Literal["char", "backspace", "space", "enter", "candidate"]
CandidateSource = Literal["llm", "cache", "fallback"]


@dataclass(slots=True)
class RawGazeSample:
    timestamp_ms: int
    gaze_vector: Sequence[float]
    head_pose: Sequence[float]
    confidence: float
    frame_id: int | None = None


@dataclass(slots=True)
class ScreenGazePoint:
    timestamp_ms: int
    x: float
    y: float
    is_valid: bool
    quality_score: float
    frame_id: int | None = None


@dataclass(slots=True)
class DwellEvent:
    timestamp_ms: int
    target_id: str
    state: DwellState
    duration_ms: int


@dataclass(slots=True)
class KeyboardAction:
    timestamp_ms: int
    action_type: ActionType
    value: str


@dataclass(slots=True)
class CandidateSuggestion:
    prefix: str
    candidates: list[str] = field(default_factory=list)
    latency_ms: int = 0
    source: CandidateSource = "fallback"
