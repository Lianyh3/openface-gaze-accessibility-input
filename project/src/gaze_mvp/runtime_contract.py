from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional


class TargetEventType(str, Enum):
    NONE = "none"
    KEY_INPUT = "key_input"
    CANDIDATE_PICK = "candidate_pick"
    BACKSPACE = "backspace"
    COMMIT_DIRECT = "commit_direct"
    CLEAR = "clear"
    CANDIDATE_REFRESH = "candidate_refresh"


@dataclass(frozen=True)
class FrameFeatures:
    """
    M0 contract object:
    raw frame-level features that can be passed from OpenFace stream to runtime core.
    """

    frame_id: int
    timestamp_ms: int
    raw_gaze_x: Optional[float] = None
    raw_gaze_y: Optional[float] = None
    confidence: Optional[float] = None
    pose_rx: Optional[float] = None
    pose_ry: Optional[float] = None
    pose_rz: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @staticmethod
    def from_dict(obj: Dict[str, object]) -> "FrameFeatures":
        return FrameFeatures(
            frame_id=int(obj["frame_id"]),
            timestamp_ms=int(obj["timestamp_ms"]),
            raw_gaze_x=(None if obj.get("raw_gaze_x") is None else float(obj["raw_gaze_x"])),
            raw_gaze_y=(None if obj.get("raw_gaze_y") is None else float(obj["raw_gaze_y"])),
            confidence=(None if obj.get("confidence") is None else float(obj["confidence"])),
            pose_rx=(None if obj.get("pose_rx") is None else float(obj["pose_rx"])),
            pose_ry=(None if obj.get("pose_ry") is None else float(obj["pose_ry"])),
            pose_rz=(None if obj.get("pose_rz") is None else float(obj["pose_rz"])),
        )


@dataclass(frozen=True)
class GazePoint:
    """
    M0 contract object:
    normalized gaze point used by hit-test / dwell logic.
    """

    timestamp_ms: int
    normalized_x: float
    normalized_y: float
    target_id: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @staticmethod
    def from_dict(obj: Dict[str, object]) -> "GazePoint":
        return GazePoint(
            timestamp_ms=int(obj["timestamp_ms"]),
            normalized_x=float(obj["normalized_x"]),
            normalized_y=float(obj["normalized_y"]),
            target_id=str(obj.get("target_id", "")),
        )


@dataclass(frozen=True)
class TargetEvent:
    """
    M0 contract object:
    event payload emitted by dwell state machine / runtime core to upper orchestration layer.
    """

    timestamp_ms: int
    event_type: TargetEventType
    target_id: str
    text: str = ""
    candidate_index: int = 0
    dwell_started_ms: int = 0
    dwell_elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["event_type"] = self.event_type.value
        return payload

    @staticmethod
    def from_dict(obj: Dict[str, object]) -> "TargetEvent":
        raw_type = str(obj.get("event_type", TargetEventType.NONE.value))
        return TargetEvent(
            timestamp_ms=int(obj["timestamp_ms"]),
            event_type=TargetEventType(raw_type),
            target_id=str(obj.get("target_id", "")),
            text=str(obj.get("text", "")),
            candidate_index=int(obj.get("candidate_index", 0)),
            dwell_started_ms=int(obj.get("dwell_started_ms", 0)),
            dwell_elapsed_ms=int(obj.get("dwell_elapsed_ms", 0)),
        )


def target_event_from_logged_event(event: Dict[str, object]) -> TargetEvent:
    """
    Convert runtime session log event object into M0 TargetEvent contract.
    This function bridges existing Python event logs to the frozen C++/Python interface.
    """

    kind = str(event.get("kind", "")).strip()
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    metrics = event.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    event_type = TargetEventType(kind if kind in {item.value for item in TargetEventType} else "none")

    timestamp_ms = int(metrics.get("emitted_at_ms", 0))
    if timestamp_ms <= 0:
        raw_utc = str(event.get("timestamp_utc", "")).strip()
        if raw_utc:
            try:
                dt = datetime.fromisoformat(raw_utc)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                timestamp_ms = int(dt.timestamp() * 1000.0)
            except ValueError:
                timestamp_ms = 0

    inferred_target = str(metrics.get("target_id", "")).strip()
    if not inferred_target:
        if kind == TargetEventType.KEY_INPUT.value:
            text = str(payload.get("text", "")).strip()
            inferred_target = f"key:{text}" if text else ""
        elif kind == TargetEventType.CANDIDATE_PICK.value:
            inferred_target = f"cand:{int(payload.get('index', 0))}"
        elif kind == TargetEventType.BACKSPACE.value:
            inferred_target = "action:back"
        elif kind == TargetEventType.COMMIT_DIRECT.value:
            inferred_target = "action:commit"
        elif kind == TargetEventType.CLEAR.value:
            inferred_target = "action:clear"
        elif kind == TargetEventType.CANDIDATE_REFRESH.value:
            inferred_target = "action:refresh"

    return TargetEvent(
        timestamp_ms=timestamp_ms,
        event_type=event_type,
        target_id=inferred_target,
        text=str(payload.get("text", "")),
        candidate_index=int(payload.get("index", 0)),
        dwell_started_ms=int(metrics.get("dwell_started_ms", 0)),
        dwell_elapsed_ms=int(metrics.get("dwell_elapsed_ms", 0)),
    )
