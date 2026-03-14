from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from gaze_mvp.gaze_runtime_pipeline import GazePointObservation
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow

ROOT = Path(__file__).resolve().parents[2]


def compile_m1_cpp(binary_path: Path) -> None:
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



def run_m1_cpp_replay(
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



def replay_event_to_flow_event(event: Dict[str, object]) -> Tuple[str, Dict[str, object]]:
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



def read_target_hit_counts(raw: object) -> Dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, int] = {}
    for key, value in raw.items():
        target_id = str(key).strip()
        if not target_id:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        out[target_id] = count
    return dict(sorted(out.items()))



def dispatch_cpp_replay_events(
    flow: KeyboardEventFlow,
    raw_events: object,
) -> tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    if not isinstance(raw_events, list):
        raise ValueError("Invalid cpp replay output: events is not list")

    emitted: List[Dict[str, object]] = []
    dispatch_errors: List[Dict[str, object]] = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue

        timestamp_ms = int(item.get("timestamp_ms", 0))
        target_id = str(item.get("target_id", ""))
        try:
            kind, payload = replay_event_to_flow_event(item)
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
    return emitted, dispatch_errors



def write_points_csv(points: Iterable[GazePointObservation], csv_path: Path) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_ms", "gaze_x", "gaze_y"])
        writer.writeheader()
        for point in points:
            writer.writerow(
                {
                    "timestamp_ms": point.timestamp_ms,
                    "gaze_x": point.gaze_x,
                    "gaze_y": point.gaze_y,
                }
            )
            count += 1
    return count
