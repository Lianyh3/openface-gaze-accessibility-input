#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.runtime_contract import (
    FrameFeatures,
    GazePoint,
    TargetEvent,
    TargetEventType,
    target_event_from_logged_event,
)


def _pick_latest_log(log_dir: Path) -> Path | None:
    patterns = [
        "keyboard_session_*.jsonl",
        "gaze_pipeline_session_*.jsonl",
        "gaze_live_session_*.jsonl",
        "keyboard_replay_session*.jsonl",
    ]
    logs: List[Path] = []
    for pattern in patterns:
        logs.extend(log_dir.glob(pattern))
    if not logs:
        return None
    logs = sorted(set(logs), key=lambda p: p.stat().st_mtime)
    return logs[-1]


def _load_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _check_samples(samples_json: Path) -> Dict[str, object]:
    data = json.loads(samples_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("samples json root must be object")
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("samples json field `cases` must be list")

    checked: List[Dict[str, object]] = []
    for i, item in enumerate(cases):
        if not isinstance(item, dict):
            raise ValueError(f"case[{i}] must be object")
        case_id = str(item.get("case_id", f"case_{i}"))
        ff = FrameFeatures.from_dict(dict(item.get("frame_features", {})))
        gp = GazePoint.from_dict(dict(item.get("gaze_point", {})))
        te = TargetEvent.from_dict(dict(item.get("target_event", {})))
        checked.append(
            {
                "case_id": case_id,
                "frame_features": ff.to_dict(),
                "gaze_point": gp.to_dict(),
                "target_event": te.to_dict(),
            }
        )
    return {
        "samples_json": str(samples_json),
        "case_count": len(checked),
        "cases": checked,
    }


def _check_session_alignment(session_log: Path, limit: int) -> Dict[str, object]:
    rows = _load_jsonl(session_log)
    converted: List[Dict[str, object]] = []
    skipped = 0
    for row in rows:
        event = row.get("event", {})
        if not isinstance(event, dict):
            skipped += 1
            continue
        target_event = target_event_from_logged_event(event)
        if target_event.event_type == TargetEventType.NONE:
            skipped += 1
            continue
        converted.append(target_event.to_dict())
        if len(converted) >= limit:
            break
    return {
        "session_log": str(session_log),
        "raw_row_count": len(rows),
        "converted_event_count": len(converted),
        "skipped_row_count": skipped,
        "events_preview": converted[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate M0 FrameFeatures/GazePoint/TargetEvent contracts.")
    parser.add_argument(
        "--samples-json",
        type=Path,
        default=ROOT / "data" / "samples" / "m0_interface_alignment_samples.json",
        help="Contract sample cases json path.",
    )
    parser.add_argument("--session-log", type=Path, default=None, help="Optional session log jsonl path.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=ROOT / "data" / "logs",
        help="Used when --session-log is omitted.",
    )
    parser.add_argument(
        "--session-limit",
        type=int,
        default=20,
        help="Maximum converted events from session log.",
    )
    parser.add_argument("--report-json", type=Path, default=None, help="Optional output report json path.")
    args = parser.parse_args()

    if not args.samples_json.exists():
        raise SystemExit(f"samples json not found: {args.samples_json}")
    if args.session_limit <= 0:
        raise SystemExit("--session-limit must be positive")

    sample_report = _check_samples(args.samples_json)

    session_log = args.session_log
    if session_log is None:
        session_log = _pick_latest_log(args.log_dir)
    if session_log is not None and not session_log.exists():
        raise SystemExit(f"session log not found: {session_log}")

    session_report = None
    if session_log is not None:
        session_report = _check_session_alignment(session_log=session_log, limit=args.session_limit)

    output = {
        "m0_contract": {
            "types": ["FrameFeatures", "GazePoint", "TargetEvent"],
            "python_contract_module": "gaze_mvp.runtime_contract",
            "cpp_header": str(ROOT / "cpp_core" / "include" / "gaze_core" / "contracts.h"),
        },
        "sample_check": sample_report,
        "session_alignment_check": session_report,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
