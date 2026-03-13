#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.candidate_pool import build_default_provider
from gaze_mvp.dwell_detector import DwellDetector, GazeObservation
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow, SessionLogger
from gaze_mvp.keyboard_mvp import KeyboardMVP
from gaze_mvp.llm_factory import build_reranker_from_config


def _read_observations(csv_path: Path) -> list[GazeObservation]:
    rows: list[GazeObservation] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"timestamp_ms", "target_id"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"CSV must contain headers: {sorted(required)}")

        for row in reader:
            ts_raw = str(row.get("timestamp_ms", "")).strip()
            target = str(row.get("target_id", "")).strip()
            if not ts_raw:
                continue
            rows.append(GazeObservation(timestamp_ms=int(float(ts_raw)), target_id=target))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay gaze target timeline and emit dwell keyboard events.")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "default.json",
        help="Path to app config.",
    )
    parser.add_argument(
        "--targets-csv",
        type=Path,
        required=True,
        help="CSV with headers: timestamp_ms,target_id",
    )
    parser.add_argument(
        "--dwell-ms",
        type=int,
        default=600,
        help="Dwell threshold in milliseconds.",
    )
    parser.add_argument(
        "--session-log",
        type=Path,
        default=ROOT / "data" / "logs" / "keyboard_replay_session.jsonl",
        help="Output jsonl event log path.",
    )
    args = parser.parse_args()

    _, reranker = build_reranker_from_config(args.config)
    keyboard = KeyboardMVP(reranker=reranker)
    flow = KeyboardEventFlow(
        keyboard=keyboard,
        candidate_provider=build_default_provider(),
        session_logger=SessionLogger(args.session_log),
    )
    detector = DwellDetector(dwell_ms=args.dwell_ms)

    observations = _read_observations(args.targets_csv)
    emitted = []
    for obs in observations:
        emission = detector.update(obs)
        if emission is None:
            continue
        state, logged_event = flow.dispatch(
            kind=emission.kind,
            payload=dict(emission.payload),
            metrics=emission.to_metrics(),
        )
        emitted.append(
            {
                "at_ms": obs.timestamp_ms,
                "event": logged_event.to_dict(),
                "state": state.to_dict(),
            }
        )

    output = {
        "targets_csv": str(args.targets_csv),
        "dwell_ms": args.dwell_ms,
        "emitted_count": len(emitted),
        "emitted": emitted,
        "final_state": keyboard.get_state().to_dict(),
        "session_log": str(args.session_log),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
