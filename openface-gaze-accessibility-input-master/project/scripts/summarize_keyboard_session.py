#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]


def _load_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _pick_latest_log(log_dir: Path) -> Path:
    patterns = [
        "keyboard_session_*.jsonl",
        "gaze_pipeline_session_*.jsonl",
        "gaze_live_session_*.jsonl",
        "keyboard_replay_session*.jsonl",
    ]
    log_map = {}
    for pattern in patterns:
        for path in log_dir.glob(pattern):
            log_map[str(path)] = path
    logs = sorted(log_map.values(), key=lambda p: p.stat().st_mtime)
    if not logs:
        raise FileNotFoundError(f"No keyboard session logs found in: {log_dir}")
    return logs[-1]


def _quantile(values: List[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if q <= 0.0:
        return min(values)
    if q >= 1.0:
        return max(values)
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    w = pos - lo
    return ordered[lo] * (1.0 - w) + ordered[hi] * w


def _summarize_durations(values: List[float]) -> Dict[str, float] | None:
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "p50": _quantile(values, 0.5),
        "p90": _quantile(values, 0.9),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize keyboard MVP session log (jsonl).")
    parser.add_argument(
        "--session-log",
        type=Path,
        default=None,
        help="Path to a keyboard session jsonl log. If omitted, use latest in --log-dir.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=ROOT / "data" / "logs",
        help="Directory containing keyboard/gaze session jsonl files.",
    )
    parser.add_argument("--report-json", type=Path, default=None, help="Optional output report path.")
    args = parser.parse_args()

    session_log = args.session_log if args.session_log is not None else _pick_latest_log(args.log_dir)
    rows = _load_jsonl(session_log)
    if not rows:
        raise SystemExit(f"Session log is empty: {session_log}")

    kind_counter = Counter()
    picked_counter = Counter()
    exposure_counter = Counter()
    dwell_elapsed_ms_values: List[float] = []
    candidate_exposure_total = 0
    candidate_exposure_event_count = 0
    backspace_count = 0
    undo_backspace_count = 0
    final_after = rows[-1].get("after", {})

    for row in rows:
        event = row.get("event", {})
        kind = str(event.get("kind", "unknown"))
        kind_counter[kind] += 1
        payload = event.get("payload", {})
        metrics = event.get("metrics", {})
        analysis = row.get("analysis", {})

        if kind == "candidate_pick":
            picked = str(payload.get("picked_candidate", "")).strip()
            if picked:
                picked_counter[picked] += 1
        if kind == "backspace":
            backspace_count += 1
            if str(analysis.get("backspace_scope", "")) == "committed_text":
                undo_backspace_count += 1

        exposed = analysis.get("exposed_candidates", [])
        if isinstance(exposed, list):
            candidates = [str(item).strip() for item in exposed if str(item).strip()]
            if candidates:
                candidate_exposure_event_count += 1
            candidate_exposure_total += len(candidates)
            for item in candidates:
                exposure_counter[item] += 1

        dwell_raw = metrics.get("dwell_elapsed_ms")
        if isinstance(dwell_raw, (int, float)):
            dwell_elapsed_ms_values.append(float(dwell_raw))

    report = {
        "session_log": str(session_log),
        "event_count": len(rows),
        "event_kinds": dict(kind_counter),
        "top_picked_candidates": picked_counter.most_common(5),
        "interaction_metrics": {
            "candidate_exposure_total": candidate_exposure_total,
            "candidate_exposure_event_count": candidate_exposure_event_count,
            "candidate_exposure_unique_count": len(exposure_counter),
            "top_exposed_candidates": exposure_counter.most_common(8),
            "dwell_trigger_count": len(dwell_elapsed_ms_values),
            "dwell_elapsed_ms_summary": _summarize_durations(dwell_elapsed_ms_values),
            "backspace_count": backspace_count,
            "undo_backspace_count": undo_backspace_count,
        },
        "final_state": {
            "committed_text": final_after.get("committed_text", ""),
            "composing_buffer": final_after.get("composing_buffer", ""),
            "rerank_source": final_after.get("rerank_source", ""),
        },
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
