from __future__ import annotations

from dataclasses import dataclass

from gaze_keyboard.common.contracts import ScreenGazePoint
from gaze_keyboard.system.keyboard_layout import KeyRect


@dataclass(slots=True)
class HitTester:
    keys: list[KeyRect]

    def locate(self, point: ScreenGazePoint) -> str | None:
        if not point.is_valid:
            return None

        for key in self.keys:
            if key.contains(point.x, point.y):
                return key.key_id
        return None
