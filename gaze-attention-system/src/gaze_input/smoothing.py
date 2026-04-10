"""注视方向平滑算法。

提供四种策略用于论文对比实验：
  1. NoSmooth      — 不做平滑（基线）
  2. EMASmooth     — 指数移动平均
  3. AdaptiveEMA   — 线性自适应 EMA（本项目实时优化推荐）
  4. OneEuroSmooth — One Euro Filter（自适应低通滤波）

参考文献:
  Casiez G, Roussel N, Vogel D. 1€ Filter: A Simple Speed-based
  Low-pass Filter for Noisy Input in Interactive Systems. CHI 2012.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


# ── 统一接口 ──────────────────────────────────────────────

class Smoother(ABC):
    """平滑器抽象基类。"""

    @abstractmethod
    def reset(self) -> None:
        """重置内部状态。"""

    @abstractmethod
    def smooth(self, value: float, timestamp: float | None = None) -> float:
        """输入原始值，返回平滑后的值。"""


# ── 1. 无平滑（基线） ────────────────────────────────────

class NoSmooth(Smoother):
    """直接返回原始值，用作对比基线。"""

    def reset(self) -> None:
        pass

    def smooth(self, value: float, timestamp: float | None = None) -> float:
        return value


# ── 2. 指数移动平均 (EMA) ─────────────────────────────────

class EMASmooth(Smoother):
    """指数移动平均平滑器。

    公式: s_t = alpha * x_t + (1 - alpha) * s_{t-1}

    alpha 越大，跟随越快但平滑效果越弱；
    alpha 越小，越平滑但延迟越大。
    """

    def __init__(self, alpha: float = 0.3):
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha 必须在 (0, 1] 范围内，当前值: {alpha}")
        self.alpha = alpha
        self._last: float | None = None

    def reset(self) -> None:
        self._last = None

    def smooth(self, value: float, timestamp: float | None = None) -> float:
        if self._last is None:
            self._last = value
        else:
            self._last = self.alpha * value + (1.0 - self.alpha) * self._last
        return self._last


# ── 3. One Euro Filter ───────────────────────────────────

class _LowPassFilter:
    """一阶低通滤波器，供 One Euro Filter 内部使用。"""

    def __init__(self, alpha: float = 1.0):
        self._alpha = alpha
        self._initialized = False
        self._hat_x_prev: float = 0.0

    def reset(self) -> None:
        self._initialized = False

    @property
    def hat_x_prev(self) -> float:
        return self._hat_x_prev

    def __call__(self, value: float, alpha: float | None = None) -> float:
        if alpha is not None:
            self._alpha = alpha
        if not self._initialized:
            self._initialized = True
            self._hat_x_prev = value
        else:
            self._hat_x_prev = self._alpha * value + (1.0 - self._alpha) * self._hat_x_prev
        return self._hat_x_prev


class AdaptiveEMASmooth(Smoother):
    """线性自适应 EMA（实时视线优化推荐）。

    思路：根据相邻帧变化量线性调整 alpha：
      alpha = alpha_min + (alpha_max - alpha_min) * clip(delta / delta_ref, 0, 1)

    - 注视稳定时（delta 小）→ alpha 低，增强平滑
    - 注视快速变化时（delta 大）→ alpha 高，降低拖尾
    """

    def __init__(
        self,
        alpha_min: float = 0.12,
        alpha_max: float = 0.65,
        delta_ref: float = 0.03,
    ):
        if not (0.0 < alpha_min <= alpha_max <= 1.0):
            raise ValueError(
                f"alpha_min/alpha_max 必须满足 0<min<=max<=1，当前: {alpha_min}, {alpha_max}"
            )
        if delta_ref <= 0:
            raise ValueError(f"delta_ref 必须 > 0，当前: {delta_ref}")

        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.delta_ref = delta_ref
        self._last_raw: float | None = None
        self._last_smooth: float | None = None

    def reset(self) -> None:
        self._last_raw = None
        self._last_smooth = None

    def smooth(self, value: float, timestamp: float | None = None) -> float:
        if self._last_smooth is None:
            self._last_raw = value
            self._last_smooth = value
            return value

        delta = abs(value - (self._last_raw if self._last_raw is not None else value))
        ratio = min(1.0, delta / self.delta_ref)
        alpha = self.alpha_min + (self.alpha_max - self.alpha_min) * ratio

        self._last_raw = value
        self._last_smooth = alpha * value + (1.0 - alpha) * self._last_smooth
        return self._last_smooth


class OneEuroSmooth(Smoother):
    """One Euro Filter — 自适应低通滤波器。

    核心思想：
      - 信号变化慢时（静止注视），使用低截止频率 → 强平滑，消除抖动
      - 信号变化快时（快速扫视），使用高截止频率 → 弱平滑，减少延迟

    参数:
      min_cutoff: 最小截止频率 (Hz)，越小越平滑。默认 1.0
      beta:       速度系数，越大对速度变化越敏感。默认 0.007
      d_cutoff:   导数的截止频率 (Hz)。默认 1.0
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self._x_filter = _LowPassFilter()
        self._dx_filter = _LowPassFilter()
        self._last_timestamp: float | None = None

    def reset(self) -> None:
        self._x_filter.reset()
        self._dx_filter.reset()
        self._last_timestamp = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        """根据截止频率和时间步长计算 alpha。"""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def smooth(self, value: float, timestamp: float | None = None) -> float:
        if timestamp is None:
            raise ValueError("OneEuroSmooth 需要 timestamp 参数")

        if self._last_timestamp is None:
            # 第一帧，无法计算导数
            self._last_timestamp = timestamp
            self._dx_filter(0.0)
            return self._x_filter(value)

        dt = timestamp - self._last_timestamp
        if dt <= 0:
            dt = 1e-6  # 防止除零
        self._last_timestamp = timestamp

        # 1. 估计信号变化速度（导数）
        dx = (value - self._x_filter.hat_x_prev) / dt
        # 对导数做低通滤波
        edx = self._dx_filter(dx, alpha=self._alpha(self.d_cutoff, dt))

        # 2. 根据速度自适应调整截止频率
        cutoff = self.min_cutoff + self.beta * abs(edx)

        # 3. 用自适应截止频率对原始信号做低通滤波
        return self._x_filter(value, alpha=self._alpha(cutoff, dt))


# ── 工厂函数 ──────────────────────────────────────────────

def create_smoother(method: str, **kwargs) -> Smoother:
    """根据配置创建平滑器实例。

    Args:
        method: "none" | "ema" | "adaptive_ema" | "one_euro"
        **kwargs: 传递给对应平滑器的参数
    """
    if method == "none":
        return NoSmooth()
    elif method == "ema":
        return EMASmooth(alpha=kwargs.get("ema_alpha", 0.3))
    elif method == "adaptive_ema":
        return AdaptiveEMASmooth(
            alpha_min=kwargs.get("adaptive_ema_alpha_min", 0.12),
            alpha_max=kwargs.get("adaptive_ema_alpha_max", 0.65),
            delta_ref=kwargs.get("adaptive_ema_delta_ref", 0.03),
        )
    elif method == "one_euro":
        return OneEuroSmooth(
            min_cutoff=kwargs.get("one_euro_min_cutoff", 1.0),
            beta=kwargs.get("one_euro_beta", 0.007),
            d_cutoff=kwargs.get("one_euro_d_cutoff", 1.0),
        )
    else:
        raise ValueError(f"未知的平滑方法: {method}")


# ── 双通道平滑器（同时平滑 x 和 y） ─────────────────────

class GazeSmoother:
    """对 gaze_angle_x 和 gaze_angle_y 分别独立平滑。"""

    def __init__(self, method: str = "one_euro", **kwargs):
        self.smoother_x = create_smoother(method, **kwargs)
        self.smoother_y = create_smoother(method, **kwargs)

    def reset(self) -> None:
        self.smoother_x.reset()
        self.smoother_y.reset()

    def smooth(
        self, gaze_x: float, gaze_y: float, timestamp: float | None = None
    ) -> tuple[float, float]:
        sx = self.smoother_x.smooth(gaze_x, timestamp)
        sy = self.smoother_y.smooth(gaze_y, timestamp)
        return sx, sy
