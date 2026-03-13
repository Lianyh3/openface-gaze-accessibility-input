from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Protocol

from gaze_mvp.dwell_detector import DwellDetector, GazeObservation
from gaze_mvp.gaze_hit_test import KeyboardHitTester
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow


@dataclass(frozen=True)
class GazePointObservation:
    timestamp_ms: int
    gaze_x: float
    gaze_y: float


@dataclass(frozen=True)
class LinearNormalizer:
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0
    clamp: bool = True

    def normalize(self, x: float, y: float) -> tuple[float, float]:
        if self.x_max == self.x_min:
            raise ValueError("x_max must be different from x_min.")
        if self.y_max == self.y_min:
            raise ValueError("y_max must be different from y_min.")

        nx = (x - self.x_min) / (self.x_max - self.x_min)
        ny = (y - self.y_min) / (self.y_max - self.y_min)

        if self.clamp:
            nx = min(1.0, max(0.0, nx))
            ny = min(1.0, max(0.0, ny))
        return nx, ny


class PointNormalizer(Protocol):
    def normalize(self, x: float, y: float) -> tuple[float, float]:
        """
        Map raw gaze coordinates into normalized keyboard coordinates.
        """


class PointSmoother(Protocol):
    def update(self, timestamp_ms: int, x: float, y: float) -> tuple[float, float]:
        """
        Smooth normalized gaze coordinates.
        """


class GazeKeyboardRuntime:
    """
    Drive keyboard flow from gaze points:
      gaze point -> hit test target_id -> dwell detector -> keyboard event dispatch.
    """

    def __init__(
        self,
        hit_tester: KeyboardHitTester,
        dwell_detector: DwellDetector,
        event_flow: KeyboardEventFlow,
        normalizer: PointNormalizer | None = None,
        smoother: PointSmoother | None = None,
    ):
        self.hit_tester = hit_tester
        self.dwell_detector = dwell_detector
        self.event_flow = event_flow
        self.normalizer = normalizer or LinearNormalizer()
        self.smoother = smoother

    def process(self, points: Iterable[GazePointObservation]) -> Dict[str, object]:
        total_points = 0
        mapped_points = 0
        target_hit_counts: Dict[str, int] = {}

        emitted: List[Dict[str, object]] = []
        dispatch_errors: List[Dict[str, object]] = []

        for point in points:
            total_points += 1
            raw_norm_x, raw_norm_y = self.normalizer.normalize(point.gaze_x, point.gaze_y)
            if self.smoother is None:
                used_x, used_y = raw_norm_x, raw_norm_y
            else:
                used_x, used_y = self.smoother.update(point.timestamp_ms, raw_norm_x, raw_norm_y)

            target_id = self.hit_tester.hit_test(used_x, used_y)
            if target_id:
                mapped_points += 1
                target_hit_counts[target_id] = target_hit_counts.get(target_id, 0) + 1

            emission = self.dwell_detector.update(
                GazeObservation(timestamp_ms=point.timestamp_ms, target_id=target_id)
            )
            if emission is None:
                continue

            kind = emission.kind
            payload = dict(emission.payload)
            try:
                state, event = self.event_flow.dispatch(
                    kind=kind,
                    payload=payload,
                    metrics=emission.to_metrics(),
                )
            except Exception as exc:
                dispatch_errors.append(
                    {
                        "timestamp_ms": point.timestamp_ms,
                        "target_id": target_id,
                        "event_kind": kind,
                        "payload": payload,
                        "error": str(exc),
                    }
                )
                continue

            emitted.append(
                {
                    "timestamp_ms": point.timestamp_ms,
                    "raw_gaze": {"x": point.gaze_x, "y": point.gaze_y},
                    "normalized_gaze_raw": {"x": raw_norm_x, "y": raw_norm_y},
                    "normalized_gaze": {"x": used_x, "y": used_y},
                    "target_id": target_id,
                    "event": event.to_dict(),
                    "state": state.to_dict(),
                }
            )

        final_state = self.event_flow.keyboard.get_state().to_dict()
        return {
            "point_count": total_points,
            "mapped_point_count": mapped_points,
            "unmapped_point_count": total_points - mapped_points,
            "target_hit_counts": dict(sorted(target_hit_counts.items())),
            "emitted_count": len(emitted),
            "emitted": emitted,
            "dispatch_error_count": len(dispatch_errors),
            "dispatch_errors": dispatch_errors,
            "final_state": final_state,
        }
