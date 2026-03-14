#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.candidate_pool import build_default_provider
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow, SessionLogger
from gaze_mvp.keyboard_mvp import KeyboardMVP
from gaze_mvp.llm_factory import build_reranker_from_config


def _default_session_log_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return ROOT / "data" / "logs" / f"gaze_cpp_pipeline_session_{stamp}.jsonl"


def _compile_cpp(binary_path: Path) -> None:
    cmd = [
        "g++",
        "-std=c++17",
        "-I",
        str(ROOT / "cpp_core" / "include"),
        str(ROOT / "cpp_core" / "src" / "apps" / "m1_runtime_replay.cpp"),
        "-o",
        str(binary_path),
    ]
    subprocess.run(cmd, check=True)


def _run_cpp_replay(
    binary_path: Path,
    gaze_csv: Path,
    timestamp_col: str,
    x_col: str,
    y_col: str,
    dwell_ms: int,
    candidate_slots: int,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    clamp: bool,
) -> Dict[str, object]:
    cmd = [
        str(binary_path),
        "--gaze-csv",
        str(gaze_csv),
        "--timestamp-col",
        timestamp_col,
        "--x-col",
        x_col,
        "--y-col",
        y_col,
        "--dwell-ms",
        str(dwell_ms),
        "--candidate-slots",
        str(candidate_slots),
        "--x-min",
        str(x_min),
        "--x-max",
        str(x_max),
        "--y-min",
        str(y_min),
        "--y-max",
        str(y_max),
    ]
    if not clamp:
        cmd.append("--no-clamp")

    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise ValueError("cpp replay output invalid: root is not object")
    return payload


def _to_flow_event(event: Dict[str, object]) -> Tuple[str, Dict[str, object]]:
    event_type = str(event.get("event_type", "")).strip()
    if event_type == "key_input":
        return "key_input", {"text": str(event.get("text", ""))}
    if event_type == "candidate_pick":
        return "candidate_pick", {"index": int(event.get("candidate_index", 0))}
    if event_type == "backspace":
        return "backspace", {}
    if event_type == "commit_direct":
        return "commit_direct", {}
    if event_type == "clear":
        return "clear", {}
    if event_type == "candidate_refresh":
        return "candidate_refresh", {}
    raise ValueError(f"Unsupported event_type from cpp replay: {event_type}")


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
        "--session-log",
        type=Path,
        default=None,
        help="Keyboard event log jsonl path. Default: auto timestamp under data/logs.",
    )
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.gaze_csv.exists():
        raise SystemExit(f"Gaze CSV not found: {args.gaze_csv}")

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

    _compile_cpp(args.cpp_binary)
    replay = _run_cpp_replay(
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
    if not isinstance(raw_events, list):
        raise SystemExit("Invalid cpp replay output: events is not list")

    emitted = []
    dispatch_errors = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue

        timestamp_ms = int(item.get("timestamp_ms", 0))
        target_id = str(item.get("target_id", ""))
        try:
            kind, payload = _to_flow_event(item)
            metrics = {
                "trigger_source": "cpp_dwell",
                "target_id": target_id,
                "dwell_started_ms": int(item.get("dwell_started_ms", 0)),
                "dwell_elapsed_ms": int(item.get("dwell_elapsed_ms", 0)),
                "emitted_at_ms": timestamp_ms,
            }
            state, event = flow.dispatch(kind=kind, payload=payload, metrics=metrics)
        except Exception as exc:
            dispatch_errors.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "target_id": target_id,
                    "raw_event": item,
                    "error": str(exc),
                }
            )
            continue

        emitted.append(
            {
                "timestamp_ms": timestamp_ms,
                "target_id": target_id,
                "event": event.to_dict(),
                "state": state.to_dict(),
            }
        )

    final_state = flow.keyboard.get_state().to_dict()
    result = {
        "point_count": int(replay.get("frame_count", 0)),
        "mapped_point_count": None,
        "unmapped_point_count": None,
        "target_hit_counts": {},
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
