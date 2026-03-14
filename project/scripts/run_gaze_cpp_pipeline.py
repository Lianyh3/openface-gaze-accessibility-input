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

from gaze_mvp.candidate_pool import build_default_provider
from gaze_mvp.cpp_runtime_bridge import (
    compile_m1_cpp,
    dispatch_cpp_replay_events,
    read_target_hit_counts,
    run_m1_cpp_replay,
)
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow, SessionLogger
from gaze_mvp.keyboard_mvp import KeyboardMVP
from gaze_mvp.llm_factory import build_reranker_from_config


def _default_session_log_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return ROOT / "data" / "logs" / f"gaze_cpp_pipeline_session_{stamp}.jsonl"



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run C++ runtime replay backend (M1 core) and dispatch into Python keyboard flow."
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
    parser.add_argument("--dwell-ms", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=8)
    parser.add_argument("--candidate-slots", type=int, default=8)
    parser.add_argument("--x-min", type=float, default=0.0)
    parser.add_argument("--x-max", type=float, default=1.0)
    parser.add_argument("--y-min", type=float, default=0.0)
    parser.add_argument("--y-max", type=float, default=1.0)
    parser.add_argument("--no-clamp", action="store_true")
    parser.add_argument(
        "--cpp-binary",
        type=Path,
        default=Path("/tmp/gaze_m1_replay"),
        help="Temporary cpp replay binary path.",
    )
    parser.add_argument(
        "--skip-cpp-build",
        action="store_true",
        help="Reuse existing C++ binary and skip g++ rebuild.",
    )
    parser.add_argument(
        "--session-log",
        type=Path,
        default=None,
        help="Keyboard event log jsonl path. Default: auto timestamp under data/logs.",
    )
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.gaze_csv.exists():
        raise SystemExit(f"Gaze CSV not found: {args.gaze_csv}")
    if args.skip_cpp_build and not args.cpp_binary.exists():
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

    if not args.skip_cpp_build:
        compile_m1_cpp(args.cpp_binary)
    replay = run_m1_cpp_replay(
        binary_path=args.cpp_binary,
        gaze_csv=args.gaze_csv,
        timestamp_col=args.timestamp_col,
        x_col=args.x_col,
        y_col=args.y_col,
        dwell_ms=dwell_ms,
        candidate_slots=args.candidate_slots,
        x_min=args.x_min,
        x_max=args.x_max,
        y_min=args.y_min,
        y_max=args.y_max,
        clamp=not args.no_clamp,
    )

    raw_events = replay.get("events", [])
    emitted, dispatch_errors = dispatch_cpp_replay_events(flow=flow, raw_events=raw_events)

    final_state = flow.keyboard.get_state().to_dict()
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
        "final_state": final_state,
    }

    output = {
        "runtime_backend": "cpp_m1",
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
        "normalization": {
            "mode": "linear_minmax",
            "x_min": args.x_min,
            "x_max": args.x_max,
            "y_min": args.y_min,
            "y_max": args.y_max,
            "clamp": not args.no_clamp,
        },
        "smoothing": {"mode": "cpp_m1_not_enabled"},
        "session_log": str(session_log),
        "cpp_replay": {
            "binary": str(args.cpp_binary),
            "row_count": int(replay.get("row_count", 0)),
            "frame_count": int(replay.get("frame_count", 0)),
            "mapped_point_count": mapped_point_count,
            "unmapped_point_count": unmapped_point_count,
            "target_hit_counts": target_hit_counts,
            "event_count": int(replay.get("event_count", len(raw_events))),
        },
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
