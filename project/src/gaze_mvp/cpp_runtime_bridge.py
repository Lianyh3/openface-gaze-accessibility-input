from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from gaze_mvp.gaze_runtime_pipeline import GazePointObservation
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow

ROOT = Path(__file__).resolve().parents[2]


def _empty_runtime_result(final_state: Dict[str, object]) -> Dict[str, object]:
    return {
        "point_count": 0,
        "mapped_point_count": 0,
        "unmapped_point_count": 0,
        "target_hit_counts": {},
        "emitted_count": 0,
        "emitted": [],
        "dispatch_error_count": 0,
        "dispatch_errors": [],
        "final_state": final_state,
    }


def _diff_hit_counts(current: Dict[str, int], previous: Dict[str, int]) -> Dict[str, int]:
    diff: Dict[str, int] = {}
    for target_id, count in current.items():
        prev = int(previous.get(target_id, 0))
        if count < prev:
            raise ValueError(f"target hit count regressed for {target_id}: {count} < {prev}")
        delta = count - prev
        if delta > 0:
            diff[target_id] = delta
    return dict(sorted(diff.items()))


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


def preprocess_points(
    points: Sequence[GazePointObservation],
    normalizer: object,
    smoother: object | None,
) -> List[GazePointObservation]:
    processed: List[GazePointObservation] = []
    for point in points:
        used_x, used_y = normalizer.normalize(point.gaze_x, point.gaze_y)
        if smoother is not None:
            used_x, used_y = smoother.update(point.timestamp_ms, used_x, used_y)
        processed.append(
            GazePointObservation(
                timestamp_ms=point.timestamp_ms,
                gaze_x=used_x,
                gaze_y=used_y,
            )
        )
    return processed


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


class IncrementalCppReplayRuntime:
    def __init__(
        self,
        flow: KeyboardEventFlow,
        normalizer: object,
        smoother: object | None,
        dwell_ms: int,
        candidate_slots: int,
        cpp_binary: Path,
        replay_csv_path: Path,
        skip_cpp_build: bool = False,
    ):
        self.flow = flow
        self.normalizer = normalizer
        self.smoother = smoother
        self.dwell_ms = dwell_ms
        self.candidate_slots = candidate_slots
        self.cpp_binary = cpp_binary
        self.replay_csv_path = replay_csv_path
        self._buffered_points: List[GazePointObservation] = []
        self._processed_event_count = 0
        self._previous_frame_count = 0
        self._previous_mapped_point_count = 0
        self._previous_unmapped_point_count = 0
        self._previous_target_hit_counts: Dict[str, int] = {}
        self._replay_invocation_count = 0
        self._last_replay: Dict[str, object] = {}

        if skip_cpp_build:
            if not self.cpp_binary.exists():
                raise ValueError(f"C++ binary not found: {self.cpp_binary}")
        else:
            compile_m1_cpp(self.cpp_binary)

    def process(self, points: Sequence[GazePointObservation]) -> Dict[str, object]:
        raw_points = list(points)
        if not raw_points:
            return _empty_runtime_result(self.flow.keyboard.get_state().to_dict())

        processed_points = preprocess_points(raw_points, normalizer=self.normalizer, smoother=self.smoother)
        if not processed_points:
            return _empty_runtime_result(self.flow.keyboard.get_state().to_dict())

        self._buffered_points.extend(processed_points)
        write_points_csv(self._buffered_points, self.replay_csv_path)
        replay = run_m1_cpp_replay(
            binary_path=self.cpp_binary,
            gaze_csv=self.replay_csv_path,
            timestamp_col="timestamp_ms",
            x_col="gaze_x",
            y_col="gaze_y",
            dwell_ms=self.dwell_ms,
            candidate_slots=self.candidate_slots,
            x_min=0.0,
            x_max=1.0,
            y_min=0.0,
            y_max=1.0,
            clamp=False,
        )
        self._replay_invocation_count += 1

        raw_events = replay.get("events", [])
        if not isinstance(raw_events, list):
            raise ValueError("Invalid cpp replay output: events is not list")
        if len(raw_events) < self._processed_event_count:
            raise ValueError(
                f"cpp replay event count regressed: {len(raw_events)} < {self._processed_event_count}"
            )

        new_events = raw_events[self._processed_event_count :]
        emitted, dispatch_errors = dispatch_cpp_replay_events(self.flow, new_events)

        frame_count = int(replay.get("frame_count", 0))
        mapped_point_count = int(replay.get("mapped_point_count", 0))
        unmapped_point_count = int(replay.get("unmapped_point_count", 0))
        target_hit_counts = read_target_hit_counts(replay.get("target_hit_counts", {}))

        if frame_count < self._previous_frame_count:
            raise ValueError(f"cpp replay frame count regressed: {frame_count} < {self._previous_frame_count}")
        if mapped_point_count < self._previous_mapped_point_count:
            raise ValueError(
                f"cpp replay mapped point count regressed: {mapped_point_count} < {self._previous_mapped_point_count}"
            )
        if unmapped_point_count < self._previous_unmapped_point_count:
            raise ValueError(
                "cpp replay unmapped point count regressed: "
                f"{unmapped_point_count} < {self._previous_unmapped_point_count}"
            )

        partial = {
            "point_count": frame_count - self._previous_frame_count,
            "mapped_point_count": mapped_point_count - self._previous_mapped_point_count,
            "unmapped_point_count": unmapped_point_count - self._previous_unmapped_point_count,
            "target_hit_counts": _diff_hit_counts(target_hit_counts, self._previous_target_hit_counts),
            "emitted_count": len(emitted),
            "emitted": emitted,
            "dispatch_error_count": len(dispatch_errors),
            "dispatch_errors": dispatch_errors,
            "final_state": self.flow.keyboard.get_state().to_dict(),
        }

        self._processed_event_count = len(raw_events)
        self._previous_frame_count = frame_count
        self._previous_mapped_point_count = mapped_point_count
        self._previous_unmapped_point_count = unmapped_point_count
        self._previous_target_hit_counts = target_hit_counts
        self._last_replay = replay
        return partial

    def replay_summary(self) -> Dict[str, object]:
        if not self._last_replay:
            return {
                "binary": str(self.cpp_binary),
                "replay_csv": str(self.replay_csv_path),
                "replay_invocation_count": self._replay_invocation_count,
                "buffered_point_count": len(self._buffered_points),
                "row_count": 0,
                "frame_count": 0,
                "mapped_point_count": 0,
                "unmapped_point_count": 0,
                "target_hit_counts": {},
                "event_count": 0,
            }

        target_hit_counts = read_target_hit_counts(self._last_replay.get("target_hit_counts", {}))
        return {
            "binary": str(self.cpp_binary),
            "replay_csv": str(self.replay_csv_path),
            "replay_invocation_count": self._replay_invocation_count,
            "buffered_point_count": len(self._buffered_points),
            "row_count": int(self._last_replay.get("row_count", 0)),
            "frame_count": int(self._last_replay.get("frame_count", 0)),
            "mapped_point_count": int(self._last_replay.get("mapped_point_count", 0)),
            "unmapped_point_count": int(self._last_replay.get("unmapped_point_count", 0)),
            "target_hit_counts": target_hit_counts,
            "event_count": int(self._last_replay.get("event_count", 0)),
        }
