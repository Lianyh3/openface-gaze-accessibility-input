#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.calibration import CalibrationPoint, fit_affine_calibration


@dataclass(frozen=True)
class CalibrationTarget:
    point_id: int
    screen_x: float
    screen_y: float


@dataclass(frozen=True)
class RawSample:
    x: float
    y: float


class GrowingCsvGazeSource:
    def __init__(self, csv_path: Path, x_col: str, y_col: str):
        self.csv_path = csv_path
        self.x_col = x_col
        self.y_col = y_col
        self._last_row_count = 0

    def _read_all_rows(self) -> List[dict]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = set(reader.fieldnames or [])
            required = {self.x_col, self.y_col}
            missing = sorted(required - fieldnames)
            if missing:
                raise ValueError(f"Source CSV missing required columns: {missing}")
            return list(reader)

    def discard_buffer(self) -> None:
        rows = self._read_all_rows()
        self._last_row_count = len(rows)

    def read_new_samples(self) -> List[RawSample]:
        rows = self._read_all_rows()
        if len(rows) < self._last_row_count:
            # File rotated/truncated, restart cursor.
            self._last_row_count = 0

        new_rows = rows[self._last_row_count :]
        self._last_row_count = len(rows)

        out: List[RawSample] = []
        for row in new_rows:
            raw_x = str(row.get(self.x_col, "")).strip()
            raw_y = str(row.get(self.y_col, "")).strip()
            if not raw_x or not raw_y:
                continue
            try:
                out.append(RawSample(x=float(raw_x), y=float(raw_y)))
            except ValueError:
                continue
        return out


def _build_grid_targets(grid_size: int, margin: float) -> List[CalibrationTarget]:
    if grid_size < 2:
        raise ValueError("grid_size must be >= 2")
    if margin < 0.0 or margin >= 0.5:
        raise ValueError("margin must be in [0, 0.5)")

    if grid_size == 2:
        values = [margin, 1.0 - margin]
    else:
        span = (1.0 - (2.0 * margin))
        step = span / float(grid_size - 1)
        values = [margin + (step * i) for i in range(grid_size)]

    targets: List[CalibrationTarget] = []
    point_id = 1
    for y in values:
        for x in values:
            targets.append(CalibrationTarget(point_id=point_id, screen_x=x, screen_y=y))
            point_id += 1
    return targets


def _capture_window(
    source: GrowingCsvGazeSource,
    duration_seconds: float,
    poll_interval_ms: int,
) -> List[RawSample]:
    samples: List[RawSample] = []
    end_time = time.monotonic() + duration_seconds
    while time.monotonic() < end_time:
        samples.extend(source.read_new_samples())
        time.sleep(max(0.005, poll_interval_ms / 1000.0))
    samples.extend(source.read_new_samples())
    return samples


def _reduce_samples(samples: List[RawSample]) -> tuple[float, float]:
    xs = [s.x for s in samples]
    ys = [s.y for s in samples]
    return statistics.median(xs), statistics.median(ys)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect online 9-point calibration samples from a growing gaze CSV.")
    parser.add_argument("--source-csv", type=Path, required=True, help="Growing CSV path with raw gaze columns.")
    parser.add_argument("--x-col", type=str, default="gaze_x", help="Source CSV x column name.")
    parser.add_argument("--y-col", type=str, default="gaze_y", help="Source CSV y column name.")
    parser.add_argument("--grid-size", type=int, default=3, help="Grid size. 3 means 9-point calibration.")
    parser.add_argument("--margin", type=float, default=0.1, help="Normalized screen margin for grid targets.")
    parser.add_argument("--point-duration-seconds", type=float, default=1.2, help="Capture duration per target.")
    parser.add_argument("--poll-interval-ms", type=int, default=40, help="Polling interval for new source rows.")
    parser.add_argument("--min-samples", type=int, default=8, help="Minimum samples required per target.")
    parser.add_argument("--retry-limit", type=int, default=2, help="Max retries per target when samples are insufficient.")
    parser.add_argument("--auto-start", action="store_true", help="Do not wait for Enter before each target.")
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "data" / "calibration" / "sessions" / "latest_calibration_points.csv",
        help="Path to save collected calibration points (raw_x/raw_y/screen_x/screen_y).",
    )
    parser.add_argument(
        "--fit-json",
        type=Path,
        default=ROOT / "data" / "calibration" / "latest_affine_calibration.json",
        help="Path to save fitted affine calibration JSON.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=ROOT / "data" / "reports" / "latest_calibration_collection_report.json",
        help="Path to save collection report JSON.",
    )
    args = parser.parse_args()

    if args.point_duration_seconds <= 0:
        raise SystemExit("--point-duration-seconds must be positive.")
    if args.min_samples <= 0:
        raise SystemExit("--min-samples must be positive.")
    if args.retry_limit < 0:
        raise SystemExit("--retry-limit must be >= 0.")

    targets = _build_grid_targets(grid_size=args.grid_size, margin=args.margin)
    source = GrowingCsvGazeSource(csv_path=args.source_csv, x_col=args.x_col, y_col=args.y_col)

    print("[calib] online collection started")
    print(f"[calib] source_csv={args.source_csv}")
    print(f"[calib] targets={len(targets)} duration={args.point_duration_seconds}s min_samples={args.min_samples}")
    print("[calib] Please follow each target instruction in order.")

    collected_rows: List[dict] = []
    calibration_points: List[CalibrationPoint] = []

    for target in targets:
        collected = False
        for attempt in range(1, args.retry_limit + 2):
            if args.auto_start:
                print(
                    f"[target {target.point_id}/{len(targets)}] auto capture start at "
                    f"(screen_x={target.screen_x:.3f}, screen_y={target.screen_y:.3f}), attempt={attempt}"
                )
            else:
                input(
                    f"[target {target.point_id}/{len(targets)}] look at "
                    f"(x={target.screen_x:.3f}, y={target.screen_y:.3f}), press Enter to capture..."
                )

            source.discard_buffer()
            start_utc = dt.datetime.now(dt.timezone.utc)
            samples = _capture_window(
                source=source,
                duration_seconds=args.point_duration_seconds,
                poll_interval_ms=args.poll_interval_ms,
            )
            end_utc = dt.datetime.now(dt.timezone.utc)

            if len(samples) < args.min_samples:
                print(
                    f"[target {target.point_id}] insufficient samples: {len(samples)} < {args.min_samples}. "
                    f"attempt={attempt}/{args.retry_limit + 1}"
                )
                continue

            raw_x, raw_y = _reduce_samples(samples)
            row = {
                "point_id": target.point_id,
                "screen_x": target.screen_x,
                "screen_y": target.screen_y,
                "raw_x": raw_x,
                "raw_y": raw_y,
                "sample_count": len(samples),
                "capture_start_utc": start_utc.isoformat(),
                "capture_end_utc": end_utc.isoformat(),
            }
            collected_rows.append(row)
            calibration_points.append(
                CalibrationPoint(raw_x=raw_x, raw_y=raw_y, screen_x=target.screen_x, screen_y=target.screen_y)
            )
            print(
                f"[target {target.point_id}] ok samples={len(samples)} "
                f"raw=({raw_x:.6f},{raw_y:.6f})"
            )
            collected = True
            break

        if not collected:
            raise SystemExit(f"Failed to collect enough samples for target {target.point_id}.")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "point_id",
                "screen_x",
                "screen_y",
                "raw_x",
                "raw_y",
                "sample_count",
                "capture_start_utc",
                "capture_end_utc",
            ],
        )
        writer.writeheader()
        writer.writerows(collected_rows)

    calibration, metrics = fit_affine_calibration(calibration_points, clamp=True)
    fit_payload = {
        "type": "affine_2d",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "point_count": len(calibration_points),
        "model": calibration.to_dict(),
        "fit_metrics": metrics.to_dict(),
        "source_points_csv": str(args.output_csv),
    }

    args.fit_json.parent.mkdir(parents=True, exist_ok=True)
    args.fit_json.write_text(json.dumps(fit_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "source_csv": str(args.source_csv),
        "x_col": args.x_col,
        "y_col": args.y_col,
        "grid_size": args.grid_size,
        "target_count": len(targets),
        "point_duration_seconds": args.point_duration_seconds,
        "min_samples": args.min_samples,
        "retry_limit": args.retry_limit,
        "output_points_csv": str(args.output_csv),
        "fit_json": str(args.fit_json),
        "fit_metrics": metrics.to_dict(),
    }

    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
