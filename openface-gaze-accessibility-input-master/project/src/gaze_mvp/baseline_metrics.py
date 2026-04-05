from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import mean
from typing import Dict, List


@dataclass
class BaselineMetrics:
    total_frames: int
    success_frames: int
    success_rate: float
    mean_confidence: float
    valid_gaze_rows: int
    valid_pose_rows: int

    def to_dict(self) -> Dict[str, float | int]:
        return asdict(self)


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_baseline_metrics(rows: List[Dict[str, str]]) -> BaselineMetrics:
    total = len(rows)
    if total == 0:
        return BaselineMetrics(
            total_frames=0,
            success_frames=0,
            success_rate=0.0,
            mean_confidence=0.0,
            valid_gaze_rows=0,
            valid_pose_rows=0,
        )

    success_frames = 0
    confidences: List[float] = []
    valid_gaze_rows = 0
    valid_pose_rows = 0

    gaze_keys = ["gaze_0_x", "gaze_0_y", "gaze_0_z", "gaze_1_x", "gaze_1_y", "gaze_1_z"]
    pose_keys = ["pose_Rx", "pose_Ry", "pose_Rz"]

    for row in rows:
        success_v = _to_float(row.get("success", ""))
        confidence_v = _to_float(row.get("confidence", ""))
        if success_v is not None and success_v > 0.5:
            success_frames += 1
        if confidence_v is not None:
            confidences.append(confidence_v)

        gaze_vals = [_to_float(row.get(k, "")) for k in gaze_keys]
        pose_vals = [_to_float(row.get(k, "")) for k in pose_keys]
        if all(v is not None for v in gaze_vals):
            valid_gaze_rows += 1
        if all(v is not None for v in pose_vals):
            valid_pose_rows += 1

    return BaselineMetrics(
        total_frames=total,
        success_frames=success_frames,
        success_rate=success_frames / total,
        mean_confidence=(mean(confidences) if confidences else 0.0),
        valid_gaze_rows=valid_gaze_rows,
        valid_pose_rows=valid_pose_rows,
    )

