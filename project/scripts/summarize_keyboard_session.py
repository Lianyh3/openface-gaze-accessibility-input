#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    logs = sorted(log_dir.glob("keyboard_session_*.jsonl"))
    if not logs:
        raise FileNotFoundError(f"No keyboard session logs found in: {log_dir}")
    return logs[-1]


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
        help="Directory containing keyboard_session_*.jsonl files.",
    )
    parser.add_argument("--report-json", type=Path, default=None, help="Optional output report path.")
    args = parser.parse_args()

    session_log = args.session_log if args.session_log is not None else _pick_latest_log(args.log_dir)
    rows = _load_jsonl(session_log)
    if not rows:
        raise SystemExit(f"Session log is empty: {session_log}")

    kind_counter = Counter()
    picked_counter = Counter()
    final_after = rows[-1].get("after", {})

    for row in rows:
        event = row.get("event", {})
        kind = str(event.get("kind", "unknown"))
        kind_counter[kind] += 1

        if kind == "candidate_pick":
            payload = event.get("payload", {})
            picked = str(payload.get("picked_candidate", "")).strip()
            if picked:
                picked_counter[picked] += 1

    report = {
        "session_log": str(session_log),
        "event_count": len(rows),
        "event_kinds": dict(kind_counter),
        "top_picked_candidates": picked_counter.most_common(5),
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
