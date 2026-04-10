"""规则引擎 — 基于持续时间与多信号融合的注意力判断（基线方案）。"""

from __future__ import annotations

from .label_schema import AttentionLabel
from .feature_extractor import FeatureWindow


class RuleEngine:
    """较稳健的规则判断：避免短时偏离被过度判罚。"""

    def __init__(
        self,
        gaze_mild: float = 0.15,
        gaze_severe: float = 0.3,
        yaw_threshold: float = 20.0,
        pitch_threshold: float = 15.0,
        severe_duration_sec: float = 8.0,
        distracted_duration_sec: float = 2.0,
        severe_decay_rate: float = 2.5,
        distracted_decay_rate: float = 2.0,
    ):
        self.gaze_mild = gaze_mild
        self.gaze_severe = gaze_severe
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.severe_duration_sec = severe_duration_sec
        self.distracted_duration_sec = distracted_duration_sec
        self.severe_decay_rate = severe_decay_rate
        self.distracted_decay_rate = distracted_decay_rate

        # 时间累积器：只有“持续偏离”才升级标签
        self._severe_accum_sec = 0.0
        self._distracted_accum_sec = 0.0

    def reset(self) -> None:
        self._severe_accum_sec = 0.0
        self._distracted_accum_sec = 0.0

    def judge(self, feat: FeatureWindow) -> tuple[AttentionLabel, str]:
        """返回 (标签, 触发原因)。"""
        window_sec = max(0.1, feat.window_end - feat.window_start)

        # 强信号（严重偏离）
        strong_gaze = feat.gaze_deviation_mean > self.gaze_severe
        strong_head = (
            feat.head_yaw_max > self.yaw_threshold * 1.2
            or feat.head_pitch_max > self.pitch_threshold * 1.2
        )

        # 中等信号（轻度偏离）
        mild_gaze = feat.gaze_deviation_mean > self.gaze_mild
        mild_head = (
            feat.head_yaw_max > self.yaw_threshold * 0.8
            or feat.head_pitch_max > self.pitch_threshold * 0.8
        )

        strong_count = int(strong_gaze) + int(strong_head)
        mild_count = int(mild_gaze) + int(mild_head)

        # 1) 强双信号：可直接判严重走神（避免漏检）
        if strong_count >= 2:
            self._severe_accum_sec += window_sec
            self._distracted_accum_sec += window_sec
            return AttentionLabel.SEVERELY_DISTRACTED, "注视与头姿同时严重异常"

        # 2) 单强信号：累计到 severe_duration 才判严重
        if strong_count == 1:
            self._severe_accum_sec += window_sec
        else:
            # 回归时更快释放 severe 累积，避免“已经专注但长期卡在严重走神”
            self._severe_accum_sec = max(0.0, self._severe_accum_sec - window_sec * self.severe_decay_rate)

        if self._severe_accum_sec >= self.severe_duration_sec:
            if strong_gaze:
                return AttentionLabel.SEVERELY_DISTRACTED, "注视严重偏离持续过久"
            return AttentionLabel.SEVERELY_DISTRACTED, "头姿严重异常持续过久"

        # 3) 中等信号：累计到 distracted_duration 才判走神
        if mild_count >= 1:
            self._distracted_accum_sec += window_sec
        else:
            # 回归时中度累积也快速衰减，提升从“走神”恢复到“专注”的响应
            self._distracted_accum_sec = max(0.0, self._distracted_accum_sec - window_sec * self.distracted_decay_rate)

        if self._distracted_accum_sec >= self.distracted_duration_sec:
            if mild_gaze and mild_head:
                return AttentionLabel.DISTRACTED, "注视和头姿持续轻度偏离"
            if mild_gaze:
                return AttentionLabel.DISTRACTED, "注视持续偏离"
            return AttentionLabel.DISTRACTED, "头姿持续偏离"

        # 4) 默认专注（把短暂扫视视作正常行为）
        return AttentionLabel.FOCUSED, "专注（短时偏离已容忍）"
