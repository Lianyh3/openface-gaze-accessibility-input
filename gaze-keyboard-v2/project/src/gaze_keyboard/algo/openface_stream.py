from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from gaze_keyboard.common.config import OpenFaceCsvConfig
from gaze_keyboard.common.contracts import RawGazeSample


@dataclass(slots=True)
class CsvCursor:
    offset: int = 0
    headers: list[str] | None = None
    carry_line: str = ""


class OpenFaceCsvPoller:
    """Poll OpenFace CSV append-only output and yield new samples.

    Notes:
    - Supports incremental reads by file offset.
    - Handles partially-written trailing lines using carry_line.
    - Parses rows with a fixed header discovered on first poll.
    """

    def __init__(self, config: OpenFaceCsvConfig) -> None:
        self.config = config
        self.cursor = CsvCursor()

    def poll_once(self) -> list[RawGazeSample]:
        csv_path = self.config.csv_path
        if not csv_path.exists() or csv_path.stat().st_size == 0:
            return []

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            if self.cursor.offset > handle.seek(0, io.SEEK_END):
                # File rotated/truncated, reset state.
                self.cursor = CsvCursor()

            handle.seek(self.cursor.offset)
            chunk = handle.read()
            self.cursor.offset = handle.tell()

        if not chunk:
            return []

        text = self.cursor.carry_line + chunk
        lines = text.splitlines(keepends=True)

        complete_lines: list[str] = []
        carry = ""
        for line in lines:
            if line.endswith("\n") or line.endswith("\r"):
                complete_lines.append(line)
            else:
                carry += line
        self.cursor.carry_line = carry

        if not complete_lines:
            return []

        if self.cursor.headers is None:
            header_line = complete_lines.pop(0).strip()
            if not header_line:
                return []
            self.cursor.headers = next(csv.reader([header_line]))

        if not self.cursor.headers:
            return []

        rows: list[RawGazeSample] = []
        for line in complete_lines:
            row_text = line.strip()
            if not row_text:
                continue

            values = next(csv.reader([row_text]), [])
            if len(values) != len(self.cursor.headers):
                continue

            row = dict(zip(self.cursor.headers, values))
            sample = self._row_to_sample(row)
            if sample is not None:
                rows.append(sample)

        return rows

    def iter_forever(self) -> Iterator[list[RawGazeSample]]:
        interval_seconds = self.config.poll_interval_ms / 1000.0
        while True:
            yield self.poll_once()
            time.sleep(interval_seconds)

    def _row_to_sample(self, row: dict[str, str]) -> RawGazeSample | None:
        try:
            timestamp = int(float(row.get(self.config.timestamp_column, "0")) * 1000)
            confidence = float(row.get(self.config.confidence_column, "0"))
            frame_raw = row.get(self.config.frame_column)
            frame_id = int(frame_raw) if frame_raw else None

            gaze_vector = _parse_vector(row, ["gaze_0_x", "gaze_0_y", "gaze_0_z"])
            head_pose = _parse_vector(row, ["pose_Rx", "pose_Ry", "pose_Rz"])

            return RawGazeSample(
                timestamp_ms=timestamp,
                gaze_vector=gaze_vector,
                head_pose=head_pose,
                confidence=confidence,
                frame_id=frame_id,
            )
        except (TypeError, ValueError):
            return None


def _parse_vector(row: dict[str, str], keys: list[str]) -> list[float]:
    values: list[float] = []
    for key in keys:
        raw = row.get(key)
        values.append(float(raw) if raw not in (None, "") else 0.0)
    return values
