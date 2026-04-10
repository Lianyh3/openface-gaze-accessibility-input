"""主窗口 — 整合注意力仪表盘和控制面板。"""

from __future__ import annotations

import json
import logging
import time
import math
from collections import deque
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QMessageBox,
)
from PySide6.QtCore import QTimer, Qt

from gui.attention_dashboard import AttentionDashboard
from src.gaze_input.openface_runner import OpenFaceRunner
from src.gaze_input.csv_parser import CsvParser
from src.gaze_input.smoothing import GazeSmoother
from src.gaze_input.feature_extractor import FeatureExtractor
from src.gaze_input.rule_engine import RuleEngine
from src.gaze_input.gpt_analyzer import GptAnalyzer
from src.gaze_input.label_schema import AttentionLabel

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """课堂注意力检测系统主窗口。"""

    def __init__(self, config_path: Path):
        super().__init__()
        self.setWindowTitle("课堂注意力检测系统")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("background-color: #1e1e1e;")

        # 加载配置
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 初始化组件（延迟到 start 时）
        self.runner: OpenFaceRunner | None = None
        self.parser: CsvParser | None = None
        self.smoother: GazeSmoother | None = None
        self.extractor: FeatureExtractor | None = None
        self.rule_engine: RuleEngine | None = None
        self.gpt_analyzer: GptAnalyzer | None = None

        self._running = False
        self._frame_count = 0
        self._last_gpt_time = 0.0

        # 实时抖动量估计：最近 N 帧注视偏离标准差
        self._jitter_window: deque[float] = deque(maxlen=45)  # 约 1.5 秒@30fps

        # 启动后的短时自校准（防止“盯着摄像头却一直严重走神”）
        self._calibration_frames_target = 45
        self._calibration_count = 0
        self._calib_sum_gx = 0.0
        self._calib_sum_gy = 0.0
        self._calib_sum_rx = 0.0
        self._calib_sum_ry = 0.0
        self._calibrated = False
        self._neutral_gaze_x = 0.0
        self._neutral_gaze_y = 0.0
        self._neutral_pose_rx = 0.0
        self._neutral_pose_ry = 0.0

        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # 左侧：控制面板
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_layout = QVBoxLayout(left_panel)

        # 平滑算法选择
        left_layout.addWidget(QLabel("平滑算法:"))
        self.smooth_combo = QComboBox()
        self.smooth_combo.addItems(["none", "ema", "adaptive_ema", "one_euro"])
        self.smooth_combo.setCurrentText(self.config["smoothing"].get("method", "adaptive_ema"))
        left_layout.addWidget(self.smooth_combo)

        # 判断路径选择
        left_layout.addWidget(QLabel("判断路径:"))
        self.judge_combo = QComboBox()
        self.judge_combo.addItems(["规则引擎", "GPT"])
        left_layout.addWidget(self.judge_combo)

        left_layout.addSpacing(20)

        # 开始/停止按钮
        self.start_btn = QPushButton("开始检测")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 10px; font-size: 16px; }"
            "QPushButton:hover { background-color: #45a049; }"
        )
        self.start_btn.clicked.connect(self._toggle_detection)
        left_layout.addWidget(self.start_btn)

        left_layout.addStretch()
        layout.addWidget(left_panel)

        # 右侧：注意力仪表盘
        self.dashboard = AttentionDashboard()
        layout.addWidget(self.dashboard, stretch=1)

    def _init_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_frame)

    def _toggle_detection(self):
        if self._running:
            self._stop_detection()
        else:
            self._start_detection()

    def _start_detection(self):
        try:
            # 初始化 OpenFace
            of_cfg = self.config["openface"]
            self.runner = OpenFaceRunner(
                bin_path=of_cfg["bin_path"],
                device=of_cfg["device"],
                output_dir=of_cfg["output_dir"],
                mloc=of_cfg.get("mloc"),
            )
            csv_path = self.runner.start()

            # 初始化处理管线
            feat_cfg = self.config["feature"]
            self.parser = CsvParser(csv_path, feat_cfg["confidence_threshold"])

            smooth_cfg = self.config["smoothing"]
            self.smoother = GazeSmoother(
                method=self.smooth_combo.currentText(),
                ema_alpha=smooth_cfg["ema_alpha"],
                one_euro_min_cutoff=smooth_cfg["one_euro_min_cutoff"],
                one_euro_beta=smooth_cfg["one_euro_beta"],
                one_euro_d_cutoff=smooth_cfg["one_euro_d_cutoff"],
            )

            self.extractor = FeatureExtractor(
                window_size_sec=feat_cfg["window_size_sec"],
                min_valid_ratio=feat_cfg["min_valid_frame_ratio"],
                baseline_x=feat_cfg["gaze_baseline_x"],
                baseline_y=feat_cfg["gaze_baseline_y"],
            )

            rule_cfg = self.config["rule_engine"]
            self.rule_engine = RuleEngine(
                gaze_mild=rule_cfg["gaze_deviation_mild"],
                gaze_severe=rule_cfg["gaze_deviation_severe"],
                yaw_threshold=rule_cfg["head_yaw_threshold"],
                pitch_threshold=rule_cfg["head_pitch_threshold"],
                severe_duration_sec=rule_cfg.get("severe_duration_sec", 8.0),
                distracted_duration_sec=rule_cfg.get("distracted_duration_sec", 2.0),
                severe_decay_rate=rule_cfg.get("severe_decay_rate", 2.5),
                distracted_decay_rate=rule_cfg.get("distracted_decay_rate", 2.0),
            )

            gpt_cfg = self.config["gpt"]
            self.gpt_analyzer = GptAnalyzer(
                model=gpt_cfg["model"],
                api_key_env=gpt_cfg["api_key_env"],
                temperature=gpt_cfg["temperature"],
                timeout=gpt_cfg["timeout_sec"],
                fallback_engine=self.rule_engine,
            )

            self._running = True
            self._frame_count = 0
            self._last_gpt_time = 0.0
            self._jitter_window.clear()
            self.dashboard.trajectory.clear()
            self.dashboard.update_status(AttentionLabel.UNCERTAIN, "检测中...")
            self.dashboard.update_stats(0, 0.0, 0.0)

            # 重置自校准状态
            self._calibration_count = 0
            self._calib_sum_gx = 0.0
            self._calib_sum_gy = 0.0
            self._calib_sum_rx = 0.0
            self._calib_sum_ry = 0.0
            self._calibrated = False
            self._neutral_gaze_x = 0.0
            self._neutral_gaze_y = 0.0
            self._neutral_pose_rx = 0.0
            self._neutral_pose_ry = 0.0

            self.start_btn.setText("停止检测")
            self.start_btn.setStyleSheet(
                "QPushButton { background-color: #f44336; color: white; padding: 10px; font-size: 16px; }"
            )
            self.timer.start(33)  # ~30fps

        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))
            log.exception("启动检测失败")

    def _stop_detection(self):
        self.timer.stop()
        if self.runner:
            self.runner.stop()
            self.runner = None
        self._running = False
        self.start_btn.setText("开始检测")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 10px; font-size: 16px; }"
        )

    def _process_frame(self):
        if not self.parser:
            return

        frames = self.parser.read_new_frames()
        for frame in frames:
            self._frame_count += 1

            # 平滑
            sx, sy = self.smoother.smooth(
                frame.gaze_angle_x, frame.gaze_angle_y, frame.timestamp
            )

            # 启动后短时自校准：用户盯摄像头时建立个体中性基线
            if not self._calibrated and self._calibration_count < self._calibration_frames_target:
                self._calibration_count += 1
                self._calib_sum_gx += sx
                self._calib_sum_gy += sy
                self._calib_sum_rx += frame.pose_Rx
                self._calib_sum_ry += frame.pose_Ry

                if self._calibration_count >= self._calibration_frames_target:
                    n = float(self._calibration_count)
                    self._neutral_gaze_x = self._calib_sum_gx / n
                    self._neutral_gaze_y = self._calib_sum_gy / n
                    self._neutral_pose_rx = self._calib_sum_rx / n
                    self._neutral_pose_ry = self._calib_sum_ry / n
                    self._calibrated = True
                    log.info(
                        "自校准完成: gaze=(%.4f, %.4f), pose=(%.4f, %.4f)",
                        self._neutral_gaze_x,
                        self._neutral_gaze_y,
                        self._neutral_pose_rx,
                        self._neutral_pose_ry,
                    )

            # 中心化：消除个体天然视线偏置 / 摄像头安装偏置
            cx = sx - self._neutral_gaze_x
            cy = sy - self._neutral_gaze_y

            # 更新轨迹图（显示中心化后的视线）
            self.dashboard.add_gaze_point(cx, cy)

            # 记录实时抖动（注视偏离）
            deviation = math.sqrt(cx * cx + cy * cy)
            self._jitter_window.append(deviation)

            # 更新特征提取器（中心化后的 gaze + 头姿相对中性位）
            frame.gaze_angle_x = cx
            frame.gaze_angle_y = cy
            frame.pose_Rx = frame.pose_Rx - self._neutral_pose_rx
            frame.pose_Ry = frame.pose_Ry - self._neutral_pose_ry
            self.extractor.push(frame)

        # 提取窗口特征并判断
        feat = self.extractor.extract()
        if feat is None:
            return

        now = time.time()
        gpt_cfg = self.config["gpt"]
        use_gpt = self.judge_combo.currentText() == "GPT"
        latency = 0.0

        if use_gpt and (now - self._last_gpt_time) >= gpt_cfg["call_interval_sec"]:
            self._last_gpt_time = now
            label, reason, _ = self.gpt_analyzer.judge(feat)
            latency = self.gpt_analyzer.last_latency_ms
        else:
            label, reason = self.rule_engine.judge(feat)

        if not self._calibrated:
            remain = max(0, self._calibration_frames_target - self._calibration_count)
            self.dashboard.update_status(AttentionLabel.UNCERTAIN, f"正在自校准，请注视摄像头... ({remain}帧)")
        else:
            self.dashboard.update_status(label, reason)

        jitter_std = 0.0
        if len(self._jitter_window) >= 2:
            vals = list(self._jitter_window)
            m = sum(vals) / len(vals)
            jitter_std = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))

        self.dashboard.update_stats(self._frame_count, latency, jitter_std)

    def closeEvent(self, event):
        self._stop_detection()
        event.accept()
