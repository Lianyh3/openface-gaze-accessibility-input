"""CSV 增量读取器。

实时读取 OpenFace 输出的 CSV，支持半行容错和低置信度过滤。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# OpenFace CSV 中我们需要的列名
REQUIRED_COLUMNS = [
    "frame", "timestamp", "confidence", "success",
    "gaze_angle_x", "gaze_angle_y",
    "pose_Rx", "pose_Ry", "pose_Rz",
    "AU45_r",
]


@dataclass
class FrameData:
    """单帧数据。"""
    frame: int
    timestamp: float
    confidence: float
    success: bool
    gaze_angle_x: float
    gaze_angle_y: float
    pose_Rx: float
    pose_Ry: float
    pose_Rz: float
    au45: float  # 眨眼强度


class CsvParser:
    """增量读取 OpenFace CSV，自动跳过不完整行和低置信度帧。"""

    def __init__(self, csv_path: Path, confidence_threshold: float = 0.7):
        self.csv_path = csv_path
        self.confidence_threshold = confidence_threshold
        self._file_pos: int = 0  # 文件读取位置（字节）
        self._header: list[str] | None = None
        self._col_idx: dict[str, int] = {}
        self._pending_line: str = ""  # 上次残留的半行

    def read_new_frames(self) -> list[FrameData]:
        """读取自上次以来的新帧数据。"""
        if not self.csv_path.exists():
            return []

        with open(self.csv_path, "r", encoding="utf-8") as f:
            f.seek(self._file_pos)
            raw = f.read()
            self._file_pos = f.tell()

        if not raw:
            return []

        # 拼接残留半行
        chunk = self._pending_line + raw
        self._pending_line = ""

        # 若当前块不以换行结尾，最后一行可能未写完，留待下次解析
        if not chunk.endswith("\n"):
            parts = chunk.split("\n")
            self._pending_line = parts.pop() if parts else chunk
            lines = parts
        else:
            lines = chunk.split("\n")

        # 首次读取，解析表头
        if self._header is None:
            if not lines:
                return []
            header_line = lines.pop(0).strip()
            if not header_line:
                return []
            self._header = [c.strip() for c in header_line.split(",")]
            self._col_idx = {name: i for i, name in enumerate(self._header)}
            missing = [c for c in REQUIRED_COLUMNS if c not in self._col_idx]
            if missing:
                log.warning("CSV 缺少列: %s", missing)

        frames: list[FrameData] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                cols = [c.strip() for c in line.split(",")]
                if self._header is None or len(cols) < len(self._header):
                    continue

                def _get(name: str) -> str:
                    return cols[self._col_idx[name]]

                confidence = float(_get("confidence"))
                success = int(float(_get("success")))

                # 过滤低置信度和失败帧
                if not success or confidence < self.confidence_threshold:
                    continue

                frame = FrameData(
                    frame=int(float(_get("frame"))),
                    timestamp=float(_get("timestamp")),
                    confidence=confidence,
                    success=bool(success),
                    gaze_angle_x=float(_get("gaze_angle_x")),
                    gaze_angle_y=float(_get("gaze_angle_y")),
                    pose_Rx=float(_get("pose_Rx")),
                    pose_Ry=float(_get("pose_Ry")),
                    pose_Rz=float(_get("pose_Rz")),
                    au45=float(_get("AU45_r")),
                )
                frames.append(frame)
            except (ValueError, KeyError, IndexError):
                continue

        return frames
