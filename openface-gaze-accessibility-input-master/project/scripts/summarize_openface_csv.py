#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.baseline_metrics import compute_baseline_metrics
from gaze_mvp.csv_schema import load_openface_csv, validate_required_columns


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize OpenFace CSV metrics.")
    parser.add_argument("--csv", type=Path, required=True, help="Path to OpenFace output csv.")
    parser.add_argument("--report-json", type=Path, default=None, help="Optional output report json path.")
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")

    data = load_openface_csv(args.csv)
    schema = validate_required_columns(data.headers)
    metrics = compute_baseline_metrics(data.rows).to_dict()

    report = {
        "csv_path": str(args.csv),
        "row_count": len(data.rows),
        "required_columns": schema,
        "metrics": metrics,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

