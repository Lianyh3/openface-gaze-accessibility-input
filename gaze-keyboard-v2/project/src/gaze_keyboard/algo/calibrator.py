from __future__ import annotations

from dataclasses import dataclass

from gaze_keyboard.common.contracts import RawGazeSample, ScreenGazePoint


@dataclass(slots=True)
class LinearCalibrator:
    """Map gaze vector to normalized screen coordinates using simple affine scales."""

    scale_x: float = 0.5
    scale_y: float = -0.5
    bias_x: float = 0.5
    bias_y: float = 0.5
    min_confidence: float = 0.6

    def map_sample(self, sample: RawGazeSample) -> ScreenGazePoint:
        if sample.confidence < self.min_confidence or len(sample.gaze_vector) < 2:
            return ScreenGazePoint(
                timestamp_ms=sample.timestamp_ms,
                x=0.0,
                y=0.0,
                is_valid=False,
                quality_score=max(0.0, min(sample.confidence, 1.0)),
                frame_id=sample.frame_id,
            )

        gx = float(sample.gaze_vector[0])
        gy = float(sample.gaze_vector[1])

        x = _clamp(gx * self.scale_x + self.bias_x, 0.0, 1.0)
        y = _clamp(gy * self.scale_y + self.bias_y, 0.0, 1.0)

        return ScreenGazePoint(
            timestamp_ms=sample.timestamp_ms,
            x=x,
            y=y,
            is_valid=True,
            quality_score=max(0.0, min(sample.confidence, 1.0)),
            frame_id=sample.frame_id,
        )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
