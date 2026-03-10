from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class TargetRegion:
    target_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    label: str = ""

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1

    def to_dict(self) -> Dict[str, object]:
        return {
            "target_id": self.target_id,
            "label": self.label,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }


class KeyboardHitTester:
    """
    Map normalized gaze points (x,y in [0,1]) to keyboard target IDs.
    """

    def __init__(self, regions: Sequence[TargetRegion]):
        if not regions:
            raise ValueError("regions must not be empty.")
        self.regions = list(regions)

    def hit_test(self, x: float, y: float) -> str:
        if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
            return ""
        for region in self.regions:
            if region.contains(x, y):
                return region.target_id
        return ""

    def layout_summary(self) -> List[Dict[str, object]]:
        return [region.to_dict() for region in self.regions]


@dataclass(frozen=True)
class LayoutPreset:
    candidate_slots: int = 8


def _add_grid_regions(
    out: List[TargetRegion],
    target_ids: Sequence[str],
    labels: Sequence[str],
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    columns: int,
) -> None:
    if columns <= 0:
        raise ValueError("columns must be positive")
    if len(target_ids) != len(labels):
        raise ValueError("target_ids and labels length mismatch")
    if not target_ids:
        return

    rows = ceil(len(target_ids) / columns)
    cell_w = (x1 - x0) / columns
    cell_h = (y1 - y0) / rows

    for idx, target_id in enumerate(target_ids):
        row = idx // columns
        col = idx % columns
        rx0 = x0 + col * cell_w
        rx1 = rx0 + cell_w
        ry0 = y0 + row * cell_h
        ry1 = ry0 + cell_h
        out.append(
            TargetRegion(
                target_id=target_id,
                label=labels[idx],
                x0=rx0,
                y0=ry0,
                x1=rx1,
                y1=ry1,
            )
        )


def build_default_hit_tester(preset: LayoutPreset | None = None) -> KeyboardHitTester:
    preset = preset or LayoutPreset()
    if preset.candidate_slots <= 0:
        raise ValueError("candidate_slots must be positive.")
    if preset.candidate_slots > 8:
        raise ValueError("current default layout supports at most 8 candidate slots.")

    regions: List[TargetRegion] = []

    candidate_ids = [f"cand:{i}" for i in range(1, preset.candidate_slots + 1)]
    candidate_labels = [f"候选{i}" for i in range(1, preset.candidate_slots + 1)]
    _add_grid_regions(
        out=regions,
        target_ids=candidate_ids,
        labels=candidate_labels,
        x0=0.0,
        x1=1.0,
        y0=0.0,
        y1=0.24,
        columns=4,
    )

    key_labels = [
        "我",
        "今天",
        "想",
        "去",
        "你",
        "现在",
        "需要",
        "请",
        "帮",
        "打开",
        "发送",
        "消息",
    ]
    key_ids = [f"key:{label}" for label in key_labels]
    _add_grid_regions(
        out=regions,
        target_ids=key_ids,
        labels=key_labels,
        x0=0.0,
        x1=1.0,
        y0=0.24,
        y1=0.82,
        columns=4,
    )

    action_labels = ["退格", "清空", "刷新候选", "提交"]
    action_ids = [
        "action:back",
        "action:clear",
        "action:refresh",
        "action:commit",
    ]
    _add_grid_regions(
        out=regions,
        target_ids=action_ids,
        labels=action_labels,
        x0=0.0,
        x1=1.0,
        y0=0.82,
        y1=1.0,
        columns=4,
    )

    return KeyboardHitTester(regions=regions)
