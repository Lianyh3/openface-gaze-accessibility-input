#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.candidate_pool import build_default_provider
from gaze_mvp.calibration import load_affine_calibration
from gaze_mvp.cpp_runtime_bridge import (
    compile_m1_cpp,
    dispatch_cpp_replay_events,
    read_target_hit_counts,
    run_m1_cpp_replay,
    write_points_csv,
)
from gaze_mvp.dwell_detector import DwellDetector
from gaze_mvp.gaze_hit_test import LayoutPreset, build_default_hit_tester
from gaze_mvp.gaze_smoothing import EmaSmoother2D, OneEuroSmoother2D
from gaze_mvp.gaze_runtime_pipeline import GazeKeyboardRuntime, GazePointObservation, LinearNormalizer
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow, SessionLogger
from gaze_mvp.keyboard_mvp import KeyboardMVP
from gaze_mvp.llm_factory import build_reranker_from_config


def _default_session_log_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return ROOT / "data" / "logs" / f"gaze_pipeline_session_{stamp}.jsonl"



def _read_points(csv_path: Path, timestamp_col: str, x_col: str, y_col: str) -> list[GazePointObservation]:
    rows: list[GazePointObservation] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [name for name in (timestamp_col, x_col, y_col) if name not in set(reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        for row in reader:
            ts_raw = str(row.get(timestamp_col, "")).strip()
            x_raw = str(row.get(x_col, "")).strip()
            y_raw = str(row.get(y_col, "")).strip()
            if not ts_raw or not x_raw or not y_raw:
                continue
            rows.append(
                GazePointObservation(
                    timestamp_ms=int(float(ts_raw)),
                    gaze_x=float(x_raw),
                    gaze_y=float(y_raw),
                )
            )
    return rows



def _preprocess_points(
    points: list[GazePointObservation],
    normalizer: object,
    smoother: object | None,
) -> list[GazePointObservation]:
    normalized_points: list[GazePointObservation] = []
    for point in points:
        used_x, used_y = normalizer.normalize(point.gaze_x, point.gaze_y)
        if smoother is not None:
            used_x, used_y = smoother.update(point.timestamp_ms, used_x, used_y)
        normalized_points.append(
            GazePointObservation(
                timestamp_ms=point.timestamp_ms,
                gaze_x=used_x,
                gaze_y=used_y,
            )
        )
    return normalized_points



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run gaze->hit-test->dwell->keyboard pipeline from gaze coordinate CSV."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "default.json",
        help="Path to app config.",
    )
    parser.add_argument(
        "--gaze-csv",
        type=Path,
        required=True,
        help="CSV containing timestamp and gaze coordinates.",
    )
    parser.add_argument("--timestamp-col", type=str, default="timestamp_ms")
    parser.add_argument("--x-col", type=str, default="gaze_x")
    parser.add_argument("--y-col", type=str, default="gaze_y")
    parser.add_argument(
        "--runtime-backend",
        choices=("python", "cpp"),
        default="python",
        help="Runtime backend for hit-test+dwell stage.",
    )
    parser.add_argument(
        "--dwell-ms",
        type=int,
        default=None,
        help="Override dwell threshold ms. Default from config.dwell_ms.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=8,
        help="Max candidate list size passed into keyboard event flow.",
    )
    parser.add_argument(
        "--candidate-slots",
        type=int,
        default=8,
        help="Candidate hit-test slot count in layout (<=8 in current preset).",
    )
    parser.add_argument(
        "--calibration-json",
        type=Path,
        default=None,
        help="Optional affine calibration JSON (fit via fit_9point_calibration.py).",
    )
    parser.add_argument(
        "--smoothing",
        choices=("none", "ema", "one_euro"),
        default="none",
        help="Optional temporal smoothing for normalized gaze coordinates.",
    )
    parser.add_argument(
        "--ema-alpha",
        type=float,
        default=0.4,
        help="EMA alpha in (0,1], used when --smoothing ema.",
    )
    parser.add_argument(
        "--one-euro-min-cutoff",
        type=float,
        default=1.0,
        help="OneEuro min_cutoff (>0), used when --smoothing one_euro.",
    )
    parser.add_argument(
        "--one-euro-beta",
        type=float,
        default=0.01,
        help="OneEuro beta (>=0), used when --smoothing one_euro.",
    )
    parser.add_argument(
        "--one-euro-d-cutoff",
        type=float,
        default=1.0,
        help="OneEuro derivative cutoff (>0), used when --smoothing one_euro.",
    )
    parser.add_argument(
        "--x-min",
        type=float,
        default=0.0,
        help="Raw x lower bound mapped to normalized 0.",
    )
    parser.add_argument(
        "--x-max",
        type=float,
        default=1.0,
        help="Raw x upper bound mapped to normalized 1.",
    )
    parser.add_argument(
        "--y-min",
        type=float,
        default=0.0,
        help="Raw y lower bound mapped to normalized 0.",
    )
    parser.add_argument(
        "--y-max",
        type=float,
        default=1.0,
        help="Raw y upper bound mapped to normalized 1.",
    )
    parser.add_argument(
        "--no-clamp",
        action="store_true",
        help="Disable normalized coordinate clamping to [0,1].",
    )
    parser.add_argument(
        "--cpp-binary",
        type=Path,
        default=Path("/tmp/gaze_m1_replay"),
        help="Temporary cpp replay binary path used when --runtime-backend cpp.",
    )
    parser.add_argument(
        "--skip-cpp-build",
        action="store_true",
        help="Reuse existing C++ binary and skip g++ rebuild when using cpp backend.",
    )
    parser.add_argument(
        "--session-log",
        type=Path,
        default=None,
        help="Keyboard event log jsonl path. Default: auto timestamp under data/logs.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Optional output report path.",
    )
    args = parser.parse_args()

    if not args.gaze_csv.exists():
        raise SystemExit(f"Gaze CSV not found: {args.gaze_csv}")
    if args.calibration_json is not None and not args.calibration_json.exists():
        raise SystemExit(f"Calibration JSON not found: {args.calibration_json}")
    if args.runtime_backend == "cpp" and args.skip_cpp_build and not args.cpp_binary.exists():
        raise SystemExit(f"C++ binary not found: {args.cpp_binary}")

    config, reranker = build_reranker_from_config(args.config)
    dwell_ms = args.dwell_ms if args.dwell_ms is not None else config.dwell_ms

    keyboard = KeyboardMVP(reranker=reranker)
    session_log = args.session_log if args.session_log is not None else _default_session_log_path()
    flow = KeyboardEventFlow(
        keyboard=keyboard,
        candidate_provider=build_default_provider(),
        session_logger=SessionLogger(session_log),
        candidate_limit=args.candidate_limit,
    )

    hit_tester = build_default_hit_tester(LayoutPreset(candidate_slots=args.candidate_slots))
    detector = DwellDetector(dwell_ms=dwell_ms)
    if args.calibration_json is not None:
        normalizer = load_affine_calibration(args.calibration_json)
        normalization_detail = {
            "mode": "affine_calibration",
            "calibration_json": str(args.calibration_json),
            "model": normalizer.to_dict(),
        }
    else:
        normalizer = LinearNormalizer(
            x_min=args.x_min,
            x_max=args.x_max,
            y_min=args.y_min,
            y_max=args.y_max,
            clamp=not args.no_clamp,
        )
        normalization_detail = {
            "mode": "linear_minmax",
            "x_min": args.x_min,
            "x_max": args.x_max,
            "y_min": args.y_min,
            "y_max": args.y_max,
            "clamp": not args.no_clamp,
        }

    if args.smoothing == "none":
        smoother = None
        smoothing_detail = {"mode": "none"}
    elif args.smoothing == "ema":
        smoother = EmaSmoother2D(alpha=args.ema_alpha)
        smoothing_detail = {"mode": "ema", "ema_alpha": args.ema_alpha}
    else:
        smoother = OneEuroSmoother2D(
            min_cutoff=args.one_euro_min_cutoff,
            beta=args.one_euro_beta,
            d_cutoff=args.one_euro_d_cutoff,
        )
        smoothing_detail = {
            "mode": "one_euro",
            "min_cutoff": args.one_euro_min_cutoff,
            "beta": args.one_euro_beta,
            "d_cutoff": args.one_euro_d_cutoff,
        }

    points = _read_points(
        csv_path=args.gaze_csv,
        timestamp_col=args.timestamp_col,
        x_col=args.x_col,
        y_col=args.y_col,
    )

    cpp_replay_detail = None
    if args.runtime_backend == "python":
        runtime = GazeKeyboardRuntime(
            hit_tester=hit_tester,
            dwell_detector=detector,
            event_flow=flow,
            normalizer=normalizer,
            smoother=smoother,
        )
        result = runtime.process(points)
    else:
        preprocessed_points = _preprocess_points(points=points, normalizer=normalizer, smoother=smoother)
        with tempfile.TemporaryDirectory(prefix="gaze_cpp_backend_") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            normalized_csv = temp_dir / "normalized_points.csv"
            preprocessed_point_count = write_points_csv(preprocessed_points, normalized_csv)
            if not args.skip_cpp_build:
                compile_m1_cpp(args.cpp_binary)
            replay = run_m1_cpp_replay(
                binary_path=args.cpp_binary,
                gaze_csv=normalized_csv,
                timestamp_col="timestamp_ms",
                x_col="gaze_x",
                y_col="gaze_y",
                dwell_ms=dwell_ms,
                candidate_slots=args.candidate_slots,
                x_min=0.0,
                x_max=1.0,
                y_min=0.0,
                y_max=1.0,
                clamp=False,
            )

        emitted, dispatch_errors = dispatch_cpp_replay_events(flow=flow, raw_events=replay.get("events", []))
        mapped_point_count = int(replay.get("mapped_point_count", 0))
        unmapped_point_count = int(replay.get("unmapped_point_count", 0))
        target_hit_counts = read_target_hit_counts(replay.get("target_hit_counts", {}))
        result = {
            "point_count": int(replay.get("frame_count", 0)),
            "mapped_point_count": mapped_point_count,
            "unmapped_point_count": unmapped_point_count,
            "target_hit_counts": target_hit_counts,
            "emitted_count": len(emitted),
            "emitted": emitted,
            "dispatch_error_count": len(dispatch_errors),
            "dispatch_errors": dispatch_errors,
            "final_state": flow.keyboard.get_state().to_dict(),
        }
        cpp_replay_detail = {
            "binary": str(args.cpp_binary),
            "preprocessed_point_count": preprocessed_point_count,
            "preprocess_input": {
                "normalization": normalization_detail,
                "smoothing": smoothing_detail,
            },
            "replay_input": {
                "timestamp_col": "timestamp_ms",
                "x_col": "gaze_x",
                "y_col": "gaze_y",
                "x_min": 0.0,
                "x_max": 1.0,
                "y_min": 0.0,
                "y_max": 1.0,
                "clamp": False,
            },
            "row_count": int(replay.get("row_count", 0)),
            "frame_count": int(replay.get("frame_count", 0)),
            "mapped_point_count": mapped_point_count,
            "unmapped_point_count": unmapped_point_count,
            "target_hit_counts": target_hit_counts,
            "event_count": int(replay.get("event_count", len(replay.get("events", [])))),
        }

    output = {
        "runtime_backend": args.runtime_backend,
        "config_path": str(args.config),
        "llm": {
            "provider": config.llm.provider,
            "api_style": config.llm.api_style,
            "model": config.llm.model,
        },
        "gaze_csv": str(args.gaze_csv),
        "timestamp_col": args.timestamp_col,
        "x_col": args.x_col,
        "y_col": args.y_col,
        "dwell_ms": dwell_ms,
        "candidate_limit": args.candidate_limit,
        "candidate_slots": args.candidate_slots,
        "normalization": normalization_detail,
        "smoothing": smoothing_detail,
        "session_log": str(session_log),
        "layout": hit_tester.layout_summary(),
        "cpp_replay": cpp_replay_detail,
        "result": result,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
