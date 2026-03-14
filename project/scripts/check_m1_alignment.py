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

from gaze_mvp.dwell_detector import DwellDetector, GazeObservation
from gaze_mvp.gaze_hit_test import LayoutPreset, build_default_hit_tester
from gaze_mvp.gaze_runtime_pipeline import LinearNormalizer
from gaze_mvp.runtime_contract import TargetEvent, TargetEventType


def _load_points(csv_path: Path, timestamp_col: str, x_col: str, y_col: str) -> List[Dict[str, float]]:
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


def _to_target_event_dict(kind: str, payload: Dict[str, object], target_id: str, ts: int, start: int, elapsed: int) -> Dict[str, object]:
    event_type = TargetEventType.NONE
    if kind == "key_input":
        event_type = TargetEventType.KEY_INPUT
    elif kind == "candidate_pick":
        event_type = TargetEventType.CANDIDATE_PICK
    elif kind == "backspace":
        event_type = TargetEventType.BACKSPACE
    elif kind == "commit_direct":
        event_type = TargetEventType.COMMIT_DIRECT
    elif kind == "clear":
        event_type = TargetEventType.CLEAR
    elif kind == "candidate_refresh":
        event_type = TargetEventType.CANDIDATE_REFRESH

    event = TargetEvent(
        timestamp_ms=ts,
        event_type=event_type,
        target_id=target_id,
        text=str(payload.get("text", "")),
        candidate_index=int(payload.get("index", 0)),
        dwell_started_ms=start,
        dwell_elapsed_ms=elapsed,
    )
    return event.to_dict()


def _run_python_reference(
    points: List[Dict[str, float]],
    dwell_ms: int,
    candidate_slots: int,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    clamp: bool,
) -> List[Dict[str, object]]:
    normalizer = LinearNormalizer(x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max, clamp=clamp)
    hit_tester = build_default_hit_tester(LayoutPreset(candidate_slots=candidate_slots))
    detector = DwellDetector(dwell_ms=dwell_ms)

    events: List[Dict[str, object]] = []
    for p in points:
        nx, ny = normalizer.normalize(p["gaze_x"], p["gaze_y"])
        target = hit_tester.hit_test(nx, ny)
        emission = detector.update(GazeObservation(timestamp_ms=int(p["timestamp_ms"]), target_id=target))
        if emission is None:
            continue
        events.append(
            _to_target_event_dict(
                kind=emission.kind,
                payload=dict(emission.payload),
                target_id=emission.target_id,
                ts=emission.emitted_at_ms,
                start=emission.dwell_started_ms,
                elapsed=emission.dwell_elapsed_ms,
            )
        )
    return events


def _compile_cpp(binary_path: Path) -> None:
    cmd = [
        "g++",
        "-std=c++17",
        "-I",
        str(ROOT / "cpp_core" / "include"),
        str(ROOT / "cpp_core" / "src" / "contracts.cpp"),
        str(ROOT / "cpp_core" / "src" / "runtime_m1.cpp"),
        str(ROOT / "cpp_core" / "src" / "m1_runtime_replay.cpp"),
        "-o",
        str(binary_path),
    ]
    subprocess.run(cmd, check=True)


def _run_cpp(
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
) -> List[Dict[str, object]]:
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
    events = payload.get("events", [])
    if not isinstance(events, list):
        raise ValueError("cpp output invalid: events is not list")
    return events


def _normalize_for_compare(event: Dict[str, object]) -> Dict[str, object]:
    return {
        "event_type": str(event.get("event_type", "")),
        "target_id": str(event.get("target_id", "")),
        "text": str(event.get("text", "")),
        "candidate_index": int(event.get("candidate_index", 0)),
        "dwell_elapsed_ms": int(event.get("dwell_elapsed_ms", 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check M1 C++ core alignment against Python reference.")
    parser.add_argument(
        "--gaze-csv",
        type=Path,
        default=ROOT / "data" / "samples" / "gaze_points_demo.csv",
        help="Input gaze csv for replay.",
    )
    parser.add_argument("--timestamp-col", type=str, default="timestamp_ms")
    parser.add_argument("--x-col", type=str, default="gaze_x")
    parser.add_argument("--y-col", type=str, default="gaze_y")
    parser.add_argument("--dwell-ms", type=int, default=600)
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
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.gaze_csv.exists():
        raise SystemExit(f"gaze csv not found: {args.gaze_csv}")

    clamp = not args.no_clamp
    points = _load_points(args.gaze_csv, args.timestamp_col, args.x_col, args.y_col)
    py_events = _run_python_reference(
        points=points,
        dwell_ms=args.dwell_ms,
        candidate_slots=args.candidate_slots,
        x_min=args.x_min,
        x_max=args.x_max,
        y_min=args.y_min,
        y_max=args.y_max,
        clamp=clamp,
    )

    _compile_cpp(args.cpp_binary)
    cpp_events = _run_cpp(
        binary_path=args.cpp_binary,
        gaze_csv=args.gaze_csv,
        timestamp_col=args.timestamp_col,
        x_col=args.x_col,
        y_col=args.y_col,
        dwell_ms=args.dwell_ms,
        candidate_slots=args.candidate_slots,
        x_min=args.x_min,
        x_max=args.x_max,
        y_min=args.y_min,
        y_max=args.y_max,
        clamp=clamp,
    )

    py_norm = [_normalize_for_compare(e) for e in py_events]
    cpp_norm = [_normalize_for_compare(e) for e in cpp_events]

    min_len = min(len(py_norm), len(cpp_norm))
    mismatch = []
    for i in range(min_len):
        if py_norm[i] != cpp_norm[i]:
            mismatch.append(
                {
                    "index": i,
                    "python": py_norm[i],
                    "cpp": cpp_norm[i],
                }
            )
    if len(py_norm) != len(cpp_norm):
        mismatch.append(
            {
                "count_mismatch": {
                    "python_count": len(py_norm),
                    "cpp_count": len(cpp_norm),
                }
            }
        )

    output = {
        "gaze_csv": str(args.gaze_csv),
        "python_event_count": len(py_norm),
        "cpp_event_count": len(cpp_norm),
        "mismatch_count": len(mismatch),
        "mismatch_preview": mismatch[:3],
        "python_events_preview": py_norm[:5],
        "cpp_events_preview": cpp_norm[:5],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")

    if mismatch:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
