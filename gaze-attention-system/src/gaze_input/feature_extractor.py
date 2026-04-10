"""多维特征提取与滑动窗口聚合。

从平滑后的帧数据中提取注意力相关特征，并在时间窗口内做统计聚合。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from collections import deque

from .csv_parser import FrameData


@dataclass
class FeatureWindow:
    """一个时间窗口内的聚合特征，可直接序列化为 JSON 发给 GPT。"""
    window_start: float = 0.0
    window_end: float = 0.0
    frame_count: int = 0
    valid_ratio: float = 0.0  # 有效帧占比

    # 注视偏离
    gaze_deviation_mean: float = 0.0
    gaze_deviation_std: float = 0.0
    gaze_deviation_max: float = 0.0

    # 头部姿态
    head_pitch_mean: float = 0.0   # Rx，低头为正
    head_yaw_mean: float = 0.0     # Ry，转头
    head_pitch_max: float = 0.0
    head_yaw_max: float = 0.0

    # 眨眼
    blink_intensity_mean: float = 0.0
    blink_count: int = 0  # AU45 > 0.5 的帧数（粗略估计）

    def to_dict(self) -> dict:
        return asdict(self)


class FeatureExtractor:
    """滑动窗口特征提取器。"""

    def __init__(
        self,
        window_size_sec: float = 2.0,
        min_valid_ratio: float = 0.7,
        baseline_x: float = 0.0,
        baseline_y: float = 0.0,
    ):
        self.window_size = window_size_sec
        self.min_valid_ratio = min_valid_ratio
        self.baseline_x = baseline_x
        self.baseline_y = baseline_y
        self._buffer: deque[FrameData] = deque()

    def push(self, frame: FrameData) -> None:
        """添加一帧数据到缓冲区。"""
        self._buffer.append(frame)
        # 移除超出窗口的旧帧
        cutoff = frame.timestamp - self.window_size
        while self._buffer and self._buffer[0].timestamp < cutoff:
            self._buffer.popleft()

    def extract(self) -> FeatureWindow | None:
        """从当前窗口提取聚合特征。有效帧不足时返回 None。"""
        if not self._buffer:
            return None

        buf = list(self._buffer)
        window_duration = buf[-1].timestamp - buf[0].timestamp
        if window_duration <= 0:
            return None

        # 简化实现：以窗口时长是否达到要求 + 最小帧数做有效性约束
        # 避免依赖固定 fps 假设导致误判
        if window_duration < self.window_size * 0.7:
            return None

        min_frames = max(5, int(self.window_size * 8))  # 约等价 >=8fps 的最低要求
        valid_ratio = min(1.0, len(buf) / max(1, min_frames))
        if valid_ratio < self.min_valid_ratio:
            return None

        # 计算注视偏离度
        deviations = [
            math.sqrt(
                (f.gaze_angle_x - self.baseline_x) ** 2
                + (f.gaze_angle_y - self.baseline_y) ** 2
            )
            for f in buf
        ]

        # 头部姿态（转为角度）
        pitches = [math.degrees(f.pose_Rx) for f in buf]
        yaws = [math.degrees(f.pose_Ry) for f in buf]

        # 眨眼
        blinks = [f.au45 for f in buf]
        blink_count = sum(1 for b in blinks if b > 0.5)

        return FeatureWindow(
            window_start=buf[0].timestamp,
            window_end=buf[-1].timestamp,
            frame_count=len(buf),
            valid_ratio=valid_ratio,
            gaze_deviation_mean=_mean(deviations),
            gaze_deviation_std=_std(deviations),
            gaze_deviation_max=max(deviations),
            head_pitch_mean=_mean(pitches),
            head_yaw_mean=_mean(yaws),
            head_pitch_max=max(abs(p) for p in pitches),
            head_yaw_max=max(abs(y) for y in yaws),
            blink_intensity_mean=_mean(blinks),
            blink_count=blink_count,
        )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))
