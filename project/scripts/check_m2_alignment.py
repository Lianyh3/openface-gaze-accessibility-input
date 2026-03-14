#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.calibration import fit_affine_calibration, load_calibration_points_csv
from gaze_mvp.gaze_smoothing import EmaSmoother2D, OneEuroSmoother2D


def _load_gaze_points(csv_path: Path, timestamp_col: str, x_col: str, y_col: str) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_raw = str(row.get(timestamp_col, "")).strip()
            x_raw = str(row.get(x_col, "")).strip()
            y_raw = str(row.get(y_col, "")).strip()
            if not ts_raw or not x_raw or not y_raw:
                continue
            out.append(
                {
                    "timestamp_ms": int(float(ts_raw)),
                    "gaze_x": float(x_raw),
                    "gaze_y": float(y_raw),
                }
            )
    return out


def _run_python_reference(
    calibration_csv: Path,
    gaze_csv: Path,
    raw_x_col: str,
    raw_y_col: str,
    screen_x_col: str,
    screen_y_col: str,
    timestamp_col: str,
    x_col: str,
    y_col: str,
    clamp: bool,
    ema_alpha: float,
    one_euro_min_cutoff: float,
    one_euro_beta: float,
    one_euro_d_cutoff: float,
) -> Dict[str, object]:
    calibration_points = load_calibration_points_csv(
        path=calibration_csv,
        raw_x_col=raw_x_col,
        raw_y_col=raw_y_col,
        screen_x_col=screen_x_col,
        screen_y_col=screen_y_col,
    )
    calibration, fit_metrics = fit_affine_calibration(calibration_points, clamp=clamp)

    gaze_points = _load_gaze_points(gaze_csv, timestamp_col, x_col, y_col)

    ema = EmaSmoother2D(alpha=ema_alpha)
    one = OneEuroSmoother2D(
        min_cutoff=one_euro_min_cutoff,
        beta=one_euro_beta,
        d_cutoff=one_euro_d_cutoff,
    )

    ema_trace: List[Dict[str, object]] = []
    one_trace: List[Dict[str, object]] = []
    for row in gaze_points:
        ts = int(row["timestamp_ms"])
        x = float(row["gaze_x"])
        y = float(row["gaze_y"])

        ema_x, ema_y = ema.update(ts, x, y)
        one_x, one_y = one.update(ts, x, y)

        ema_trace.append(
            {
                "timestamp_ms": ts,
                "x": ema_x,
                "y": ema_y,
            }
        )
        one_trace.append(
            {
                "timestamp_ms": ts,
                "x": one_x,
                "y": one_y,
            }
        )

    return {
        "calibration": {
            "model": calibration.to_dict(),
            "fit_metrics": fit_metrics.to_dict(),
        },
        "ema": {
            "alpha": ema_alpha,
            "trace": ema_trace,
        },
        "one_euro": {
            "min_cutoff": one_euro_min_cutoff,
            "beta": one_euro_beta,
            "d_cutoff": one_euro_d_cutoff,
            "trace": one_trace,
        },
    }


def _compile_cpp(binary_path: Path) -> None:
    cmd = [
        "g++",
        "-std=c++17",
        "-I",
        str(ROOT / "cpp_core" / "include"),
        str(ROOT / "cpp_core" / "src" / "apps" / "m2_runtime_replay.cpp"),
        "-o",
        str(binary_path),
    ]
    subprocess.run(cmd, check=True)


def _run_cpp(
    binary_path: Path,
    calibration_csv: Path,
    gaze_csv: Path,
    raw_x_col: str,
    raw_y_col: str,
    screen_x_col: str,
    screen_y_col: str,
    timestamp_col: str,
    x_col: str,
    y_col: str,
    clamp: bool,
    ema_alpha: float,
    one_euro_min_cutoff: float,
    one_euro_beta: float,
    one_euro_d_cutoff: float,
) -> Dict[str, object]:
    cmd = [
        str(binary_path),
        "--calibration-csv",
        str(calibration_csv),
        "--raw-x-col",
        raw_x_col,
        "--raw-y-col",
        raw_y_col,
        "--screen-x-col",
        screen_x_col,
        "--screen-y-col",
        screen_y_col,
        "--gaze-csv",
        str(gaze_csv),
        "--timestamp-col",
        timestamp_col,
        "--x-col",
        x_col,
        "--y-col",
        y_col,
        "--ema-alpha",
        str(ema_alpha),
        "--one-euro-min-cutoff",
        str(one_euro_min_cutoff),
        "--one-euro-beta",
        str(one_euro_beta),
        "--one-euro-d-cutoff",
        str(one_euro_d_cutoff),
    ]
    if not clamp:
        cmd.append("--no-clamp")

    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise ValueError("cpp output invalid: root is not object")
    return payload


def _float_diff(a: float, b: float) -> float:
    return abs(float(a) - float(b))


def _compare_calibration(py_obj: Dict[str, object], cpp_obj: Dict[str, object], tol: float) -> List[Dict[str, object]]:
    mismatches: List[Dict[str, object]] = []

    py_model = dict(py_obj.get("model", {}))
    cpp_model = dict(cpp_obj.get("model", {}))
    for key in ("ax", "bx", "cx", "ay", "by", "cy"):
        if key not in py_model or key not in cpp_model:
            mismatches.append({"field": f"model.{key}", "error": "missing field"})
            continue
        diff = _float_diff(float(py_model[key]), float(cpp_model[key]))
        if diff > tol:
            mismatches.append(
                {
                    "field": f"model.{key}",
                    "python": float(py_model[key]),
                    "cpp": float(cpp_model[key]),
                    "abs_diff": diff,
                }
            )

    if bool(py_model.get("clamp", True)) != bool(cpp_model.get("clamp", True)):
        mismatches.append(
            {
                "field": "model.clamp",
                "python": bool(py_model.get("clamp", True)),
                "cpp": bool(cpp_model.get("clamp", True)),
            }
        )

    py_metrics = dict(py_obj.get("fit_metrics", {}))
    cpp_metrics = dict(cpp_obj.get("fit_metrics", {}))
    if int(py_metrics.get("point_count", 0)) != int(cpp_metrics.get("point_count", 0)):
        mismatches.append(
            {
                "field": "fit_metrics.point_count",
                "python": int(py_metrics.get("point_count", 0)),
                "cpp": int(cpp_metrics.get("point_count", 0)),
            }
        )

    for key in ("mae_x", "mae_y", "rmse", "max_abs_error"):
        if key not in py_metrics or key not in cpp_metrics:
            mismatches.append({"field": f"fit_metrics.{key}", "error": "missing field"})
            continue
        diff = _float_diff(float(py_metrics[key]), float(cpp_metrics[key]))
        if diff > tol:
            mismatches.append(
                {
                    "field": f"fit_metrics.{key}",
                    "python": float(py_metrics[key]),
                    "cpp": float(cpp_metrics[key]),
                    "abs_diff": diff,
                }
            )

    return mismatches


def _compare_trace(
    name: str,
    py_trace: List[Dict[str, object]],
    cpp_trace: List[Dict[str, object]],
    tol: float,
) -> List[Dict[str, object]]:
    mismatches: List[Dict[str, object]] = []

    if len(py_trace) != len(cpp_trace):
        mismatches.append(
            {
                "trace": name,
                "field": "count",
                "python": len(py_trace),
                "cpp": len(cpp_trace),
            }
        )

    for i in range(min(len(py_trace), len(cpp_trace))):
        p = py_trace[i]
        c = cpp_trace[i]

        p_ts = int(p.get("timestamp_ms", 0))
        c_ts = int(c.get("timestamp_ms", 0))
        if p_ts != c_ts:
            mismatches.append(
                {
                    "trace": name,
                    "index": i,
                    "field": "timestamp_ms",
                    "python": p_ts,
                    "cpp": c_ts,
                }
            )

        for axis in ("x", "y"):
            diff = _float_diff(float(p.get(axis, 0.0)), float(c.get(axis, 0.0)))
            if diff > tol:
                mismatches.append(
                    {
                        "trace": name,
                        "index": i,
                        "field": axis,
                        "python": float(p.get(axis, 0.0)),
                        "cpp": float(c.get(axis, 0.0)),
                        "abs_diff": diff,
                    }
                )

    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description="Check M2 C++ core alignment against Python reference.")
    parser.add_argument(
        "--calibration-csv",
        type=Path,
        default=ROOT / "data" / "samples" / "calibration_points_9_demo.csv",
        help="Calibration CSV for affine fit.",
    )
    parser.add_argument(
        "--gaze-csv",
        type=Path,
        default=ROOT / "data" / "samples" / "gaze_points_demo.csv",
        help="Gaze CSV for smoothing replay.",
    )
    parser.add_argument("--raw-x-col", type=str, default="raw_x")
    parser.add_argument("--raw-y-col", type=str, default="raw_y")
    parser.add_argument("--screen-x-col", type=str, default="screen_x")
    parser.add_argument("--screen-y-col", type=str, default="screen_y")
    parser.add_argument("--timestamp-col", type=str, default="timestamp_ms")
    parser.add_argument("--x-col", type=str, default="gaze_x")
    parser.add_argument("--y-col", type=str, default="gaze_y")
    parser.add_argument("--no-clamp", action="store_true")

    parser.add_argument("--ema-alpha", type=float, default=0.4)
    parser.add_argument("--one-euro-min-cutoff", type=float, default=1.0)
    parser.add_argument("--one-euro-beta", type=float, default=0.01)
    parser.add_argument("--one-euro-d-cutoff", type=float, default=1.0)

    parser.add_argument("--float-tol", type=float, default=1e-6)
    parser.add_argument(
        "--cpp-binary",
        type=Path,
        default=Path("/tmp/gaze_m2_replay"),
        help="Temporary cpp replay binary path.",
    )
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.calibration_csv.exists():
        raise SystemExit(f"calibration csv not found: {args.calibration_csv}")
    if not args.gaze_csv.exists():
        raise SystemExit(f"gaze csv not found: {args.gaze_csv}")

    clamp = not args.no_clamp

    py = _run_python_reference(
        calibration_csv=args.calibration_csv,
        gaze_csv=args.gaze_csv,
        raw_x_col=args.raw_x_col,
        raw_y_col=args.raw_y_col,
        screen_x_col=args.screen_x_col,
        screen_y_col=args.screen_y_col,
        timestamp_col=args.timestamp_col,
        x_col=args.x_col,
        y_col=args.y_col,
        clamp=clamp,
        ema_alpha=args.ema_alpha,
        one_euro_min_cutoff=args.one_euro_min_cutoff,
        one_euro_beta=args.one_euro_beta,
        one_euro_d_cutoff=args.one_euro_d_cutoff,
    )

    _compile_cpp(args.cpp_binary)
    cpp = _run_cpp(
        binary_path=args.cpp_binary,
        calibration_csv=args.calibration_csv,
        gaze_csv=args.gaze_csv,
        raw_x_col=args.raw_x_col,
        raw_y_col=args.raw_y_col,
        screen_x_col=args.screen_x_col,
        screen_y_col=args.screen_y_col,
        timestamp_col=args.timestamp_col,
        x_col=args.x_col,
        y_col=args.y_col,
        clamp=clamp,
        ema_alpha=args.ema_alpha,
        one_euro_min_cutoff=args.one_euro_min_cutoff,
        one_euro_beta=args.one_euro_beta,
        one_euro_d_cutoff=args.one_euro_d_cutoff,
    )

    calibration_mismatches = _compare_calibration(
        py_obj=dict(py.get("calibration", {})),
        cpp_obj=dict(cpp.get("calibration", {})),
        tol=args.float_tol,
    )
    ema_mismatches = _compare_trace(
        name="ema",
        py_trace=list(dict(py.get("ema", {})).get("trace", [])),
        cpp_trace=list(dict(cpp.get("ema", {})).get("trace", [])),
        tol=args.float_tol,
    )
    one_euro_mismatches = _compare_trace(
        name="one_euro",
        py_trace=list(dict(py.get("one_euro", {})).get("trace", [])),
        cpp_trace=list(dict(cpp.get("one_euro", {})).get("trace", [])),
        tol=args.float_tol,
    )

    all_mismatches = calibration_mismatches + ema_mismatches + one_euro_mismatches

    output = {
        "calibration_csv": str(args.calibration_csv),
        "gaze_csv": str(args.gaze_csv),
        "float_tol": args.float_tol,
        "mismatch_count": len(all_mismatches),
        "mismatch_breakdown": {
            "calibration": len(calibration_mismatches),
            "ema": len(ema_mismatches),
            "one_euro": len(one_euro_mismatches),
        },
        "mismatch_preview": all_mismatches[:5],
        "python_preview": {
            "calibration": py.get("calibration", {}),
            "ema_trace_head": list(dict(py.get("ema", {})).get("trace", []))[:5],
            "one_euro_trace_head": list(dict(py.get("one_euro", {})).get("trace", []))[:5],
        },
        "cpp_preview": {
            "calibration": dict(cpp.get("calibration", {})),
            "ema_trace_head": list(dict(cpp.get("ema", {})).get("trace", []))[:5],
            "one_euro_trace_head": list(dict(cpp.get("one_euro", {})).get("trace", []))[:5],
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")

    if all_mismatches:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
