"""注意力仪表盘控件 — 显示状态指示灯、注视轨迹、时间线。"""

from __future__ import annotations

from collections import deque
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

from src.gaze_input.label_schema import AttentionLabel


# 状态对应的颜色
STATUS_COLORS = {
    AttentionLabel.FOCUSED: QColor(76, 175, 80),           # 绿色
    AttentionLabel.DISTRACTED: QColor(255, 193, 7),        # 黄色
    AttentionLabel.SEVERELY_DISTRACTED: QColor(244, 67, 54),  # 红色
    AttentionLabel.UNCERTAIN: QColor(158, 158, 158),       # 灰色
}

STATUS_TEXT = {
    AttentionLabel.FOCUSED: "专注",
    AttentionLabel.DISTRACTED: "走神",
    AttentionLabel.SEVERELY_DISTRACTED: "严重走神",
    AttentionLabel.UNCERTAIN: "检测中...",
}


class StatusIndicator(QFrame):
    """状态指示灯。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self._status = AttentionLabel.UNCERTAIN
        self._reason = ""

    def set_status(self, status: AttentionLabel, reason: str = ""):
        self._status = status
        self._reason = reason
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 画圆形指示灯
        color = STATUS_COLORS.get(self._status, QColor(158, 158, 158))
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(120), 3))
        painter.drawEllipse(10, 10, 100, 100)

        painter.end()


class GazeTrajectory(QFrame):
    """注视轨迹图 — 显示最近 N 个注视点。"""

    def __init__(self, max_points: int = 100, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setStyleSheet("background-color: #2d2d2d; border-radius: 8px;")
        self._points: deque[tuple[float, float]] = deque(maxlen=max_points)

    def add_point(self, x: float, y: float):
        """添加一个注视点（归一化坐标 -1 到 1）。"""
        self._points.append((x, y))
        self.update()

    def clear(self):
        self._points.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        scale = min(w, h) / 2.5

        # 画坐标轴
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawLine(int(cx), 0, int(cx), h)
        painter.drawLine(0, int(cy), w, int(cy))

        # 画注视点轨迹
        if len(self._points) < 2:
            painter.end()
            return

        points = list(self._points)
        for i, (x, y) in enumerate(points):
            alpha = int(50 + 200 * i / len(points))  # 渐变透明度
            color = QColor(66, 165, 245, alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)

            px = cx + x * scale
            py = cy - y * scale  # y 轴翻转
            radius = 3 + 4 * i / len(points)
            painter.drawEllipse(QPointF(px, py), radius, radius)

        painter.end()


class AttentionDashboard(QWidget):
    """注意力仪表盘 — 组合状态指示灯、文字、轨迹图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 状态指示灯 + 文字
        top_layout = QHBoxLayout()

        self.indicator = StatusIndicator()
        top_layout.addWidget(self.indicator)

        status_text_layout = QVBoxLayout()
        self.status_label = QLabel("检测中...")
        self.status_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
        self.reason_label = QLabel("")
        self.reason_label.setStyleSheet("font-size: 14px; color: #aaa;")
        status_text_layout.addWidget(self.status_label)
        status_text_layout.addWidget(self.reason_label)
        status_text_layout.addStretch()

        top_layout.addLayout(status_text_layout)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # 注视轨迹图
        self.trajectory = GazeTrajectory()
        layout.addWidget(self.trajectory, stretch=1)

        # 统计信息
        self.stats_label = QLabel("帧数: 0 | 延迟: 0ms")
        self.stats_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(self.stats_label)

    def update_status(self, status: AttentionLabel, reason: str = ""):
        self.indicator.set_status(status, reason)
        self.status_label.setText(STATUS_TEXT.get(status, "未知"))
        self.status_label.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {STATUS_COLORS[status].name()};"
        )
        self.reason_label.setText(reason)

    def add_gaze_point(self, x: float, y: float):
        self.trajectory.add_point(x, y)

    def update_stats(self, frame_count: int, latency_ms: float, jitter_std: float = 0.0):
        self.stats_label.setText(
            f"帧数: {frame_count} | 延迟: {latency_ms:.0f}ms | 抖动(std): {jitter_std:.4f}"
        )
