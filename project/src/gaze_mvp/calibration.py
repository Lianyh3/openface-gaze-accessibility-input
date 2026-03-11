from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class CalibrationPoint:
    raw_x: float
    raw_y: float
    screen_x: float
    screen_y: float


@dataclass(frozen=True)
class CalibrationFitMetrics:
    point_count: int
    mae_x: float
    mae_y: float
    rmse: float
    max_abs_error: float

    def to_dict(self) -> Dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class AffineCalibration:
    ax: float
    bx: float
    cx: float
    ay: float
    by: float
    cy: float
    clamp: bool = True

    def normalize(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        x = self.ax * raw_x + self.bx * raw_y + self.cx
        y = self.ay * raw_x + self.by * raw_y + self.cy
        if self.clamp:
            x = min(1.0, max(0.0, x))
            y = min(1.0, max(0.0, y))
        return x, y

    def to_dict(self) -> Dict[str, float | bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Dict[str, object]) -> "AffineCalibration":
        required = ("ax", "bx", "cx", "ay", "by", "cy")
        missing = [k for k in required if k not in obj]
        if missing:
            raise ValueError(f"Missing calibration fields: {missing}")
        return cls(
            ax=float(obj["ax"]),
            bx=float(obj["bx"]),
            cx=float(obj["cx"]),
            ay=float(obj["ay"]),
            by=float(obj["by"]),
            cy=float(obj["cy"]),
            clamp=bool(obj.get("clamp", True)),
        )


def _solve_3x3(a: Sequence[Sequence[float]], b: Sequence[float]) -> tuple[float, float, float]:
    # Gaussian elimination with partial pivoting for a 3x3 system.
    mat = [[float(a[r][c]) for c in range(3)] + [float(b[r])] for r in range(3)]

    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(mat[r][col]))
        if abs(mat[pivot][col]) < 1e-12:
            raise ValueError("Calibration matrix is singular; provide more diverse calibration points.")
        if pivot != col:
            mat[col], mat[pivot] = mat[pivot], mat[col]

        pivot_val = mat[col][col]
        for j in range(col, 4):
            mat[col][j] /= pivot_val

        for r in range(3):
            if r == col:
                continue
            factor = mat[r][col]
            if factor == 0.0:
                continue
            for j in range(col, 4):
                mat[r][j] -= factor * mat[col][j]

    return mat[0][3], mat[1][3], mat[2][3]


def fit_affine_calibration(points: Sequence[CalibrationPoint], clamp: bool = True) -> tuple[AffineCalibration, CalibrationFitMetrics]:
    if len(points) < 3:
        raise ValueError("At least 3 points are required for affine calibration.")

    s_xx = 0.0
    s_xy = 0.0
    s_yy = 0.0
    s_x1 = 0.0
    s_y1 = 0.0
    s_11 = float(len(points))

    rhs_x = [0.0, 0.0, 0.0]
    rhs_y = [0.0, 0.0, 0.0]

    for p in points:
        x = p.raw_x
        y = p.raw_y
        u = p.screen_x
        v = p.screen_y
        s_xx += x * x
        s_xy += x * y
        s_yy += y * y
        s_x1 += x
        s_y1 += y

        rhs_x[0] += x * u
        rhs_x[1] += y * u
        rhs_x[2] += u

        rhs_y[0] += x * v
        rhs_y[1] += y * v
        rhs_y[2] += v

    # Light ridge term to stabilize nearly collinear calibration points.
    ridge = 1e-8
    normal = [
        [s_xx + ridge, s_xy, s_x1],
        [s_xy, s_yy + ridge, s_y1],
        [s_x1, s_y1, s_11 + ridge],
    ]

    ax, bx, cx = _solve_3x3(normal, rhs_x)
    ay, by, cy = _solve_3x3(normal, rhs_y)

    calib = AffineCalibration(ax=ax, bx=bx, cx=cx, ay=ay, by=by, cy=cy, clamp=clamp)

    abs_x: List[float] = []
    abs_y: List[float] = []
    sq_sum = 0.0
    max_abs = 0.0
    for p in points:
        pred_x, pred_y = calib.normalize(p.raw_x, p.raw_y)
        dx = pred_x - p.screen_x
        dy = pred_y - p.screen_y
        ax_err = abs(dx)
        ay_err = abs(dy)
        abs_x.append(ax_err)
        abs_y.append(ay_err)
        sq_sum += dx * dx + dy * dy
        max_abs = max(max_abs, ax_err, ay_err)

    metrics = CalibrationFitMetrics(
        point_count=len(points),
        mae_x=(sum(abs_x) / len(abs_x)),
        mae_y=(sum(abs_y) / len(abs_y)),
        rmse=math.sqrt(sq_sum / (2.0 * len(points))),
        max_abs_error=max_abs,
    )
    return calib, metrics


def load_calibration_points_csv(
    path: Path,
    raw_x_col: str = "raw_x",
    raw_y_col: str = "raw_y",
    screen_x_col: str = "screen_x",
    screen_y_col: str = "screen_y",
) -> List[CalibrationPoint]:
    rows: List[CalibrationPoint] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = [raw_x_col, raw_y_col, screen_x_col, screen_y_col]
        missing = [name for name in required if name not in set(reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Calibration CSV missing required columns: {missing}")

        for row in reader:
            raw_x = str(row.get(raw_x_col, "")).strip()
            raw_y = str(row.get(raw_y_col, "")).strip()
            screen_x = str(row.get(screen_x_col, "")).strip()
            screen_y = str(row.get(screen_y_col, "")).strip()
            if not raw_x or not raw_y or not screen_x or not screen_y:
                continue
            rows.append(
                CalibrationPoint(
                    raw_x=float(raw_x),
                    raw_y=float(raw_y),
                    screen_x=float(screen_x),
                    screen_y=float(screen_y),
                )
            )
    return rows


def load_affine_calibration(path: Path) -> AffineCalibration:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Calibration JSON root must be an object.")

    if isinstance(obj.get("model"), dict):
        return AffineCalibration.from_dict(obj["model"])
    return AffineCalibration.from_dict(obj)
