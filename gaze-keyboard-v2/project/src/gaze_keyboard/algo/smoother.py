from __future__ import annotations

from dataclasses import dataclass

from gaze_keyboard.common.contracts import ScreenGazePoint


@dataclass(slots=True)
class EmaSmoother:
    alpha: float = 0.35
    _last_x: float | None = None
    _last_y: float | None = None

    def reset(self) -> None:
        self._last_x = None
        self._last_y = None

    def update(self, point: ScreenGazePoint) -> ScreenGazePoint:
        if not point.is_valid:
            return point

        if self._last_x is None or self._last_y is None:
            self._last_x = point.x
            self._last_y = point.y
            return point

        sx = self.alpha * point.x + (1.0 - self.alpha) * self._last_x
        sy = self.alpha * point.y + (1.0 - self.alpha) * self._last_y
        self._last_x = sx
        self._last_y = sy

        return ScreenGazePoint(
            timestamp_ms=point.timestamp_ms,
            x=sx,
            y=sy,
            is_valid=True,
            quality_score=point.quality_score,
            frame_id=point.frame_id,
        )
