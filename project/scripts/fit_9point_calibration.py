#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.calibration import fit_affine_calibration, load_calibration_points_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit affine calibration from 9-point (or more) gaze samples.")
    parser.add_argument("--points-csv", type=Path, required=True, help="CSV with raw_x,raw_y,screen_x,screen_y")
    parser.add_argument("--raw-x-col", type=str, default="raw_x")
    parser.add_argument("--raw-y-col", type=str, default="raw_y")
    parser.add_argument("--screen-x-col", type=str, default="screen_x")
    parser.add_argument("--screen-y-col", type=str, default="screen_y")
    parser.add_argument("--min-points", type=int, default=6, help="Reject fitting when valid points are fewer than this.")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "data" / "calibration" / "latest_affine_calibration.json",
        help="Path to save fitted calibration parameters.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Optional report JSON path. Defaults to output-json with _report suffix.",
    )
    parser.add_argument(
        "--no-clamp",
        action="store_true",
        help="Disable [0,1] clamping after affine mapping.",
    )
    args = parser.parse_args()

    if not args.points_csv.exists():
        raise SystemExit(f"Points CSV not found: {args.points_csv}")

    points = load_calibration_points_csv(
        path=args.points_csv,
        raw_x_col=args.raw_x_col,
        raw_y_col=args.raw_y_col,
        screen_x_col=args.screen_x_col,
        screen_y_col=args.screen_y_col,
    )
    if len(points) < args.min_points:
        raise SystemExit(f"Not enough valid points: {len(points)} < {args.min_points}")

    calibration, metrics = fit_affine_calibration(points, clamp=not args.no_clamp)

    saved = {
        "type": "affine_2d",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "point_count": len(points),
        "model": calibration.to_dict(),
        "fit_metrics": metrics.to_dict(),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = args.report_json
    if report_path is None:
        report_path = args.output_json.with_name(f"{args.output_json.stem}_report.json")

    report = {
        "points_csv": str(args.points_csv),
        "output_json": str(args.output_json),
        "fit_metrics": metrics.to_dict(),
        "columns": {
            "raw_x": args.raw_x_col,
            "raw_y": args.raw_y_col,
            "screen_x": args.screen_x_col,
            "screen_y": args.screen_y_col,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    output = {
        "saved_calibration": saved,
        "report_json": str(report_path),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
