#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.baseline_metrics import BaselineMetrics, compute_baseline_metrics
from gaze_mvp.csv_schema import load_openface_csv, validate_required_columns


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return values[0]
    if p >= 100:
        return values[-1]
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * (p / 100.0)
    lower = math.floor(idx)
    upper = math.ceil(idx)
    if lower == upper:
        return sorted_vals[lower]
    w = idx - lower
    return sorted_vals[lower] * (1.0 - w) + sorted_vals[upper] * w


@dataclass
class TimingMetrics:
    duration_seconds: float
    estimated_fps: float
    mean_frame_interval_ms: float
    p95_frame_interval_ms: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def compute_timing_metrics(rows: List[Dict[str, str]]) -> TimingMetrics:
    timestamps = [_to_float(row.get("timestamp", "")) for row in rows]
    timestamps = [v for v in timestamps if v is not None]
    if len(timestamps) < 2:
        return TimingMetrics(
            duration_seconds=0.0,
            estimated_fps=0.0,
            mean_frame_interval_ms=0.0,
            p95_frame_interval_ms=0.0,
        )

    first = timestamps[0]
    last = timestamps[-1]
    duration = max(0.0, last - first)
    intervals = [b - a for a, b in zip(timestamps, timestamps[1:]) if b >= a]
    if not intervals:
        return TimingMetrics(
            duration_seconds=duration,
            estimated_fps=0.0,
            mean_frame_interval_ms=0.0,
            p95_frame_interval_ms=0.0,
        )

    estimated_fps = ((len(timestamps) - 1) / duration) if duration > 0 else 0.0
    mean_interval_ms = statistics.mean(intervals) * 1000.0
    p95_interval_ms = _percentile(intervals, 95.0) * 1000.0

    return TimingMetrics(
        duration_seconds=duration,
        estimated_fps=estimated_fps,
        mean_frame_interval_ms=mean_interval_ms,
        p95_frame_interval_ms=p95_interval_ms,
    )


def _mean_of(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one or more OpenFace webcam CSV runs.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=ROOT / "data" / "runs" / "check_cam_defaults",
        help="Directory containing webcam_*.csv files.",
    )
    parser.add_argument(
        "--glob",
        type=str,
        default="webcam_*.csv",
        help="CSV filename pattern under --runs-dir.",
    )
    parser.add_argument("--report-json", type=Path, default=None, help="Optional output report json path.")
    args = parser.parse_args()

    csv_files = sorted(args.runs_dir.glob(args.glob))
    if not csv_files:
        raise SystemExit(f"No CSV files found: runs_dir={args.runs_dir}, glob={args.glob}")

    runs = []
    for csv_path in csv_files:
        data = load_openface_csv(csv_path)
        schema = validate_required_columns(data.headers)
        baseline = compute_baseline_metrics(data.rows)
        timing = compute_timing_metrics(data.rows)
        runs.append(
            {
                "csv_path": str(csv_path),
                "row_count": len(data.rows),
                "required_columns": schema,
                "metrics": baseline.to_dict(),
                "timing": timing.to_dict(),
            }
        )

    success_rates = [r["metrics"]["success_rate"] for r in runs]
    mean_confidences = [r["metrics"]["mean_confidence"] for r in runs]
    fps_values = [r["timing"]["estimated_fps"] for r in runs]
    durations = [r["timing"]["duration_seconds"] for r in runs]

    report = {
        "runs_dir": str(args.runs_dir),
        "glob": args.glob,
        "run_count": len(runs),
        "aggregate": {
            "mean_success_rate": _mean_of(success_rates),
            "mean_confidence": _mean_of(mean_confidences),
            "mean_estimated_fps": _mean_of(fps_values),
            "mean_duration_seconds": _mean_of(durations),
        },
        "runs": runs,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
