#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
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


def _load_csv_rows(path: Path) -> List[Dict[str, str]]:
    import csv

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _pick_latest_log(log_dir: Path) -> Path:
    patterns = [
        "keyboard_session_*.jsonl",
        "gaze_pipeline_session_*.jsonl",
        "gaze_live_session_*.jsonl",
        "keyboard_replay_session*.jsonl",
    ]
    candidates: List[Path] = []
    for pattern in patterns:
        candidates.extend(log_dir.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No session logs found in: {log_dir}")
    candidates = sorted(set(candidates), key=lambda p: p.stat().st_mtime)
    return candidates[-1]


def _parse_iso_utc(raw: object) -> dt.datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


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


def _summarize_values(values: List[float]) -> Dict[str, float] | None:
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


def _levenshtein_distance(a: str, b: str) -> int:
    n = len(a)
    m = len(b)
    if n == 0:
        return m
    if m == 0:
        return n

    prev = list(range(m + 1))
    cur = [0] * (m + 1)
    for i in range(1, n + 1):
        cur[0] = i
        ai = a[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ai == b[j - 1] else 1
            cur[j] = min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + cost,
            )
        prev, cur = cur, prev
    return prev[m]


def _resolve_path(raw: str, base_dir: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    # Prefer paths relative to CSV directory; fallback to project root.
    p1 = (base_dir / p).resolve()
    if p1.exists():
        return p1
    return (ROOT / p).resolve()


def _extract_duration_seconds(rows: List[Dict]) -> tuple[float | None, str]:
    emitted_vals: List[float] = []
    for row in rows:
        event = row.get("event", {})
        metrics = event.get("metrics", {})
        raw = metrics.get("emitted_at_ms")
        if isinstance(raw, (int, float)):
            emitted_vals.append(float(raw))

    if len(emitted_vals) >= 2:
        duration_ms = max(emitted_vals) - min(emitted_vals)
        if duration_ms > 0:
            return duration_ms / 1000.0, "event.metrics.emitted_at_ms"

    utc_vals: List[dt.datetime] = []
    for row in rows:
        event = row.get("event", {})
        t = _parse_iso_utc(event.get("timestamp_utc"))
        if t is not None:
            utc_vals.append(t)
    if len(utc_vals) >= 2:
        duration = (max(utc_vals) - min(utc_vals)).total_seconds()
        if duration > 0:
            return duration, "event.timestamp_utc"
    return None, "none"


def _evaluate_single_session(
    session_log: Path,
    target_text: str | None,
    include_composing: bool,
    task_id: str | None = None,
) -> Dict[str, object]:
    rows = _load_jsonl(session_log)
    if not rows:
        raise ValueError(f"Session log is empty: {session_log}")

    event_kinds = Counter()
    exposure_counter = Counter()
    dwell_elapsed_values: List[float] = []

    candidate_pick_count = 0
    backspace_count = 0
    undo_backspace_count = 0
    key_input_char_count = 0

    final_after = rows[-1].get("after", {})
    committed_text = str(final_after.get("committed_text", ""))
    composing_buffer = str(final_after.get("composing_buffer", ""))
    output_text = committed_text + composing_buffer if include_composing else committed_text

    for row in rows:
        event = row.get("event", {})
        analysis = row.get("analysis", {})
        kind = str(event.get("kind", "unknown"))
        payload = event.get("payload", {})
        metrics = event.get("metrics", {})

        event_kinds[kind] += 1
        if kind == "candidate_pick":
            candidate_pick_count += 1
        if kind == "backspace":
            backspace_count += 1
            if str(analysis.get("backspace_scope", "")) == "committed_text":
                undo_backspace_count += 1
        if kind == "key_input":
            key_input_char_count += len(str(payload.get("text", "")))

        exposed = analysis.get("exposed_candidates")
        if not isinstance(exposed, list):
            # Backward compatibility with older logs without "analysis".
            after = row.get("after", {})
            exposed = after.get("ranked_candidates", [])
        if isinstance(exposed, list):
            for item in exposed:
                candidate = str(item).strip()
                if candidate:
                    exposure_counter[candidate] += 1

        dwell_raw = metrics.get("dwell_elapsed_ms")
        if isinstance(dwell_raw, (int, float)):
            dwell_elapsed_values.append(float(dwell_raw))

    duration_seconds, duration_source = _extract_duration_seconds(rows)
    cpm = None
    wpm_5char = None
    wpm_space = None
    if duration_seconds is not None and duration_seconds > 0:
        minutes = duration_seconds / 60.0
        cpm = len(output_text) / minutes
        wpm_5char = cpm / 5.0
        word_count_space = len([w for w in output_text.split() if w])
        wpm_space = word_count_space / minutes

    accuracy = None
    if target_text is not None:
        dist = _levenshtein_distance(output_text, target_text)
        denom = max(1, len(target_text))
        cer = dist / denom
        accuracy = {
            "target_text": target_text,
            "output_text": output_text,
            "edit_distance": dist,
            "cer": cer,
            "char_accuracy": max(0.0, 1.0 - cer),
            "exact_match": output_text == target_text,
        }

    return {
        "task_id": task_id,
        "session_log": str(session_log),
        "event_count": len(rows),
        "event_kinds": dict(event_kinds),
        "interaction": {
            "candidate_pick_count": candidate_pick_count,
            "candidate_exposure_total": sum(exposure_counter.values()),
            "candidate_exposure_unique_count": len(exposure_counter),
            "top_exposed_candidates": exposure_counter.most_common(8),
            "backspace_count": backspace_count,
            "undo_backspace_count": undo_backspace_count,
            "key_input_char_count": key_input_char_count,
            "dwell_trigger_count": len(dwell_elapsed_values),
            "dwell_elapsed_ms_summary": _summarize_values(dwell_elapsed_values),
        },
        "final_state": {
            "committed_text": committed_text,
            "composing_buffer": composing_buffer,
            "output_text": output_text,
            "rerank_source": final_after.get("rerank_source", ""),
        },
        "timing": {
            "duration_source": duration_source,
            "duration_seconds": duration_seconds,
            "cpm": cpm,
            "wpm_5char": wpm_5char,
            "wpm_space": wpm_space,
        },
        "accuracy": accuracy,
    }


def _mean(values: List[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _aggregate(session_reports: List[Dict[str, object]]) -> Dict[str, object]:
    cer_values: List[float] = []
    cpm_values: List[float] = []
    wpm_values: List[float] = []
    dwell_mean_values: List[float] = []
    event_kinds = Counter()
    exposure_counter = Counter()
    exact_match_count = 0

    for rep in session_reports:
        for k, v in rep.get("event_kinds", {}).items():
            event_kinds[str(k)] += int(v)

        interaction = rep.get("interaction", {})
        for word, count in interaction.get("top_exposed_candidates", []):
            exposure_counter[str(word)] += int(count)
        dwell_summary = interaction.get("dwell_elapsed_ms_summary")
        if isinstance(dwell_summary, dict):
            mean_v = dwell_summary.get("mean")
            if isinstance(mean_v, (int, float)):
                dwell_mean_values.append(float(mean_v))

        timing = rep.get("timing", {})
        cpm = timing.get("cpm")
        if isinstance(cpm, (int, float)):
            cpm_values.append(float(cpm))
        wpm = timing.get("wpm_5char")
        if isinstance(wpm, (int, float)):
            wpm_values.append(float(wpm))

        accuracy = rep.get("accuracy")
        if isinstance(accuracy, dict):
            cer = accuracy.get("cer")
            if isinstance(cer, (int, float)):
                cer_values.append(float(cer))
            if bool(accuracy.get("exact_match", False)):
                exact_match_count += 1

    with_target_count = sum(1 for rep in session_reports if isinstance(rep.get("accuracy"), dict))
    return {
        "session_count": len(session_reports),
        "with_target_count": with_target_count,
        "exact_match_count": exact_match_count,
        "exact_match_rate": (exact_match_count / with_target_count) if with_target_count > 0 else None,
        "mean_cer": _mean(cer_values),
        "mean_char_accuracy": (1.0 - _mean(cer_values)) if cer_values else None,
        "mean_cpm": _mean(cpm_values),
        "mean_wpm_5char": _mean(wpm_values),
        "mean_dwell_elapsed_ms": _mean(dwell_mean_values),
        "event_kinds_total": dict(event_kinds),
        "top_exposed_candidates_overall": exposure_counter.most_common(10),
    }


def _load_task_target(tasks_csv: Path, task_id: str | None) -> tuple[str, str]:
    rows = _load_csv_rows(tasks_csv)
    if not rows:
        raise ValueError(f"tasks csv is empty: {tasks_csv}")
    required = {"task_id", "target_text"}
    missing = required - set(rows[0].keys())
    if missing:
        raise ValueError(f"tasks csv missing required headers: {sorted(missing)}")

    if task_id is None:
        first = rows[0]
        return str(first["task_id"]), str(first["target_text"])

    for row in rows:
        if str(row.get("task_id", "")).strip() == task_id:
            return str(row["task_id"]), str(row["target_text"])
    raise ValueError(f"task_id not found in tasks csv: {task_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate keyboard session(s): CER / CPM / WPM / dwell metrics.")
    parser.add_argument("--session-log", type=Path, default=None, help="Single session jsonl path.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=ROOT / "data" / "logs",
        help="Directory containing session logs.",
    )
    parser.add_argument(
        "--mapping-csv",
        type=Path,
        default=None,
        help="Batch mapping CSV with headers: session_log,target_text (optional: task_id).",
    )
    parser.add_argument(
        "--target-text",
        type=str,
        default=None,
        help="Target text for CER evaluation in single mode, or as fallback target in batch mode.",
    )
    parser.add_argument(
        "--tasks-csv",
        type=Path,
        default=None,
        help="Task definition CSV with headers: task_id,target_text. Used in single mode.",
    )
    parser.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Task id in --tasks-csv. If omitted, use first row in tasks csv.",
    )
    parser.add_argument(
        "--include-composing",
        action="store_true",
        help="Evaluate committed_text + composing_buffer as output_text.",
    )
    parser.add_argument("--report-json", type=Path, default=None, help="Optional output report path.")
    args = parser.parse_args()

    session_reports: List[Dict[str, object]] = []

    if args.mapping_csv is not None:
        rows = _load_csv_rows(args.mapping_csv)
        if not rows:
            raise SystemExit(f"mapping csv is empty: {args.mapping_csv}")
        required = {"session_log"}
        missing = required - set(rows[0].keys())
        if missing:
            raise SystemExit(f"mapping csv missing required headers: {sorted(missing)}")

        base_dir = args.mapping_csv.parent
        for row in rows:
            raw_session = str(row.get("session_log", "")).strip()
            if not raw_session:
                continue
            session_path = _resolve_path(raw_session, base_dir=base_dir)
            if not session_path.exists():
                raise SystemExit(f"session_log not found: {session_path}")

            target_text = str(row.get("target_text", "")).strip() or args.target_text
            task_id = str(row.get("task_id", "")).strip() or None
            rep = _evaluate_single_session(
                session_log=session_path,
                target_text=(target_text if target_text else None),
                include_composing=args.include_composing,
                task_id=task_id,
            )
            session_reports.append(rep)
        mode = "batch_mapping_csv"
    else:
        if args.session_log is not None:
            session_path = args.session_log
        else:
            session_path = _pick_latest_log(args.log_dir)

        if not session_path.exists():
            raise SystemExit(f"session log not found: {session_path}")

        task_id = None
        target_text = args.target_text
        if args.tasks_csv is not None:
            task_id, target_from_csv = _load_task_target(args.tasks_csv, args.task_id)
            if not target_text:
                target_text = target_from_csv

        session_reports.append(
            _evaluate_single_session(
                session_log=session_path,
                target_text=(target_text if target_text else None),
                include_composing=args.include_composing,
                task_id=task_id,
            )
        )
        mode = "single_or_latest"

    output = {
        "mode": mode,
        "include_composing": args.include_composing,
        "aggregate": _aggregate(session_reports),
        "sessions": session_reports,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
