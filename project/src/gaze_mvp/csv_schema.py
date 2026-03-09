from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


REQUIRED_COLUMNS = [
    "frame",
    "timestamp",
    "confidence",
    "success",
    "gaze_0_x",
    "gaze_0_y",
    "gaze_0_z",
    "gaze_1_x",
    "gaze_1_y",
    "gaze_1_z",
    "pose_Rx",
    "pose_Ry",
    "pose_Rz",
]


@dataclass
class OpenFaceCsv:
    path: Path
    headers: List[str]
    rows: List[Dict[str, str]]


def _clean_header(name: str) -> str:
    # OpenFace CSV header fields may contain leading spaces.
    return name.strip()


def load_openface_csv(path: Path) -> OpenFaceCsv:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        raw_headers = next(reader)
        headers = [_clean_header(h) for h in raw_headers]
        rows: List[Dict[str, str]] = []
        for raw_row in reader:
            row = {headers[i]: raw_row[i].strip() if i < len(raw_row) else "" for i in range(len(headers))}
            rows.append(row)
    return OpenFaceCsv(path=path, headers=headers, rows=rows)


def validate_required_columns(headers: List[str]) -> Dict[str, bool]:
    header_set = set(headers)
    return {col: (col in header_set) for col in REQUIRED_COLUMNS}

