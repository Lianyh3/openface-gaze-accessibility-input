#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.gaze_hit_test import LayoutPreset, build_default_hit_tester


def _now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _run_cmd(
    cmd: Sequence[str],
    cwd: Path,
    env_overrides: Dict[str, str] | None = None,
) -> int:
    print("\n[run]", " ".join(shlex.quote(p) for p in cmd))
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.run(cmd, cwd=cwd, env=env)
    return proc.returncode


def _load_tasks(tasks_csv: Path, task_ids: Sequence[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with tasks_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: str(v or "").strip() for k, v in row.items()})

    if not rows:
        raise SystemExit(f"No task rows found: {tasks_csv}")

    if not task_ids:
        return rows

    wanted = {tid.strip() for tid in task_ids if tid.strip()}
    picked = [r for r in rows if r.get("task_id", "") in wanted]
    missing = sorted(wanted - {r.get("task_id", "") for r in picked})
    if missing:
        raise SystemExit(f"Task IDs not found in {tasks_csv}: {', '.join(missing)}")
    return picked


@dataclass
class LiveRunSpec:
    backend: str
    task_id: str
    target_text: str
    repeat_index: int

    @property
    def run_id(self) -> str:
        return f"{self.backend}_{self.task_id}_r{self.repeat_index:02d}"


def _extract_single_eval_metrics(eval_json: Path) -> Dict[str, object]:
    if not eval_json.exists():
        return {
            "ok": False,
            "error": f"missing eval report: {eval_json}",
        }
    data = json.loads(eval_json.read_text(encoding="utf-8"))
    sessions = data.get("sessions") or []
    if not sessions:
        return {
            "ok": False,
            "error": "eval report has no sessions",
        }
    s0 = sessions[0]
    accuracy = s0.get("accuracy") or {}
    timing = s0.get("timing") or {}
    interaction = s0.get("interaction") or {}
    return {
        "ok": True,
        "exact_match": accuracy.get("exact_match"),
        "cer": accuracy.get("cer"),
        "char_accuracy": accuracy.get("char_accuracy"),
        "cpm": timing.get("cpm"),
        "wpm_5char": timing.get("wpm_5char"),
        "duration_seconds": timing.get("duration_seconds"),
        "event_count": s0.get("event_count"),
        "candidate_pick_count": interaction.get("candidate_pick_count"),
        "dwell_mean_ms": ((interaction.get("dwell_elapsed_ms_summary") or {}).get("mean")),
        "committed_text": ((s0.get("final_state") or {}).get("committed_text")),
        "output_text": ((s0.get("final_state") or {}).get("output_text")),
    }


def _mean(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _aggregate_live(records: Sequence[Dict[str, object]]) -> Dict[str, object]:
    done = [r for r in records if r.get("status") == "ok" and (r.get("metrics") or {}).get("ok")]

    def _agg_for(items: Sequence[Dict[str, object]]) -> Dict[str, object]:
        metrics = [i.get("metrics") or {} for i in items]
        exact_vals = [bool(m.get("exact_match")) for m in metrics if m.get("exact_match") is not None]
        cer_vals = [m.get("cer") for m in metrics if isinstance(m.get("cer"), (int, float))]
        cpm_vals = [m.get("cpm") for m in metrics if isinstance(m.get("cpm"), (int, float))]
        wpm_vals = [m.get("wpm_5char") for m in metrics if isinstance(m.get("wpm_5char"), (int, float))]
        return {
            "run_count": len(items),
            "evaluated_count": len(metrics),
            "exact_match_count": sum(1 for v in exact_vals if v),
            "exact_match_rate": (sum(1 for v in exact_vals if v) / len(exact_vals)) if exact_vals else None,
            "mean_cer": _mean([float(v) for v in cer_vals]) if cer_vals else None,
            "mean_cpm": _mean([float(v) for v in cpm_vals]) if cpm_vals else None,
            "mean_wpm_5char": _mean([float(v) for v in wpm_vals]) if wpm_vals else None,
        }

    by_backend: Dict[str, List[Dict[str, object]]] = {}
    by_task: Dict[str, List[Dict[str, object]]] = {}
    for r in done:
        by_backend.setdefault(str(r.get("backend")), []).append(r)
        by_task.setdefault(str(r.get("task_id")), []).append(r)

    return {
        "overall": _agg_for(done),
        "by_backend": {k: _agg_for(v) for k, v in sorted(by_backend.items())},
        "by_task": {k: _agg_for(v) for k, v in sorted(by_task.items())},
    }


def _build_target_center_map(candidate_slots: int) -> Dict[str, tuple[float, float]]:
    tester = build_default_hit_tester(LayoutPreset(candidate_slots=candidate_slots))
    centers: Dict[str, tuple[float, float]] = {}
    for region in tester.regions:
        centers[region.target_id] = ((region.x0 + region.x1) / 2.0, (region.y0 + region.y1) / 2.0)
    return centers


def _headless_target_plan(task_id: str, target_text: str) -> List[str]:
    # These plans are deterministic and compatible with current default layout/lexicon.
    by_task = {
        "T01": ["key:我", "key:今天", "key:想", "key:去", "action:commit", "action:refresh", "cand:7"],  # 我今天想去图书馆
        "T02": ["key:请", "key:帮", "key:我", "action:commit", "key:打开", "cand:2"],  # 请帮我打开文档
        "T03": ["key:我", "key:现在", "key:需要", "key:去", "action:commit", "action:refresh", "cand:8"],  # 我现在需要去实验室
    }
    by_text = {
        "我今天想去图书馆": by_task["T01"],
        "请帮我打开文档": by_task["T02"],
        "我现在需要去实验室": by_task["T03"],
    }

    if task_id in by_task:
        return list(by_task[task_id])
    if target_text in by_text:
        return list(by_text[target_text])
    raise ValueError(
        f"Headless replay has no preset plan for task_id={task_id}, target_text={target_text!r}. "
        "Use T01/T02/T03 or switch to execution-mode=live."
    )


def _write_headless_gaze_csv(
    csv_path: Path,
    target_ids: Sequence[str],
    center_map: Dict[str, tuple[float, float]],
    dwell_ms: int,
    step_ms: int,
) -> Dict[str, object]:
    if dwell_ms <= 0:
        raise ValueError("dwell_ms must be positive")
    if step_ms <= dwell_ms:
        raise ValueError("step_ms must be larger than dwell_ms for deterministic single-emission targets")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = 0
    row_count = 0
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "gaze_x", "gaze_y", "target_id"])
        for target_id in target_ids:
            if target_id not in center_map:
                raise ValueError(f"Unknown target_id in headless plan: {target_id}")
            x, y = center_map[target_id]
            # 3 points per target: start, mid, and past dwell threshold.
            samples = (t0, t0 + dwell_ms // 2, t0 + dwell_ms + 50)
            for ts in samples:
                writer.writerow([ts, f"{x:.6f}", f"{y:.6f}", target_id])
                row_count += 1
            t0 += step_ms
    return {
        "target_count": len(target_ids),
        "row_count": row_count,
        "step_ms": step_ms,
        "dwell_ms": dwell_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch runner for end-to-end gaze experiments: baseline + live(py/cpp) + auto evaluation."
    )
    parser.add_argument("--experiment-name", type=str, default=f"e2e_batch_{_now_stamp()}")
    parser.add_argument(
        "--execution-mode",
        choices=("live", "headless_replay"),
        default="live",
        help="live: webcam interactive runs; headless_replay: scripted gaze replay without GUI.",
    )

    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--wait-csv-seconds", type=float, default=20.0)
    parser.add_argument("--max-seconds", type=float, default=60.0)

    parser.add_argument("--baseline-runs", type=int, default=5)
    parser.add_argument("--baseline-timeout-seconds", type=int, default=25)

    parser.add_argument("--tasks-csv", type=Path, default=ROOT / "data" / "samples" / "fixed_text_tasks_v1.csv")
    parser.add_argument(
        "--task-ids",
        type=str,
        default="T01,T02",
        help="Comma-separated task IDs from tasks CSV.",
    )

    parser.add_argument("--backends", type=str, default="python,cpp", help="Comma-separated: python,cpp")
    parser.add_argument("--python-repeats", type=int, default=3)
    parser.add_argument("--cpp-repeats", type=int, default=2)

    parser.add_argument("--smoothing", choices=("none", "ema", "one_euro"), default="none")
    parser.add_argument("--ema-alpha", type=float, default=0.4)
    parser.add_argument("--one-euro-min-cutoff", type=float, default=1.0)
    parser.add_argument("--one-euro-beta", type=float, default=0.01)
    parser.add_argument("--one-euro-d-cutoff", type=float, default=1.0)
    parser.add_argument("--dwell-ms", type=int, default=600)
    parser.add_argument("--calibration-json", type=Path, default=None)
    parser.add_argument(
        "--headless-step-ms",
        type=int,
        default=1000,
        help="Timestamp stride per target when --execution-mode=headless_replay.",
    )
    parser.add_argument(
        "--force-heuristic-reranker",
        action="store_true",
        help="Unset OPENAI_API_KEY during scripted runs to keep candidate ranking deterministic.",
    )

    parser.add_argument("--print-events", action="store_true")
    parser.add_argument("--skip-cpp-build", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Do not wait for Enter between live runs.",
    )

    args = parser.parse_args()

    experiment_root = ROOT / "data" / "experiments" / args.experiment_name
    baseline_root = experiment_root / "baseline"
    live_root = experiment_root / "live"

    baseline_runs_dir = baseline_root / "runs"
    baseline_reports_dir = baseline_root / "reports"

    live_openface_dir = live_root / "openface_runs"
    live_logs_dir = live_root / "logs"
    live_pipeline_reports_dir = live_root / "pipeline_reports"
    live_eval_reports_dir = live_root / "eval_reports"
    live_synthetic_gaze_dir = live_root / "synthetic_gaze"

    for p in (
        baseline_runs_dir,
        baseline_reports_dir,
        live_openface_dir,
        live_logs_dir,
        live_pipeline_reports_dir,
        live_eval_reports_dir,
        live_synthetic_gaze_dir,
    ):
        _ensure_dir(p)

    task_ids = [x.strip() for x in args.task_ids.split(",") if x.strip()]
    tasks = _load_tasks(args.tasks_csv, task_ids)

    backends = [x.strip() for x in args.backends.split(",") if x.strip()]
    invalid_backends = [b for b in backends if b not in ("python", "cpp")]
    if invalid_backends:
        raise SystemExit(f"Unsupported backends: {', '.join(invalid_backends)}")

    manifest = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "experiment_root": str(experiment_root),
        "args": {
            "device": args.device,
            "execution_mode": args.execution_mode,
            "wait_csv_seconds": args.wait_csv_seconds,
            "max_seconds": args.max_seconds,
            "baseline_runs": args.baseline_runs,
            "baseline_timeout_seconds": args.baseline_timeout_seconds,
            "tasks_csv": str(args.tasks_csv),
            "task_ids": [t.get("task_id", "") for t in tasks],
            "backends": backends,
            "python_repeats": args.python_repeats,
            "cpp_repeats": args.cpp_repeats,
            "smoothing": args.smoothing,
            "ema_alpha": args.ema_alpha,
            "one_euro_min_cutoff": args.one_euro_min_cutoff,
            "one_euro_beta": args.one_euro_beta,
            "one_euro_d_cutoff": args.one_euro_d_cutoff,
            "dwell_ms": args.dwell_ms,
            "calibration_json": str(args.calibration_json) if args.calibration_json else None,
            "headless_step_ms": args.headless_step_ms,
            "force_heuristic_reranker": args.force_heuristic_reranker,
            "print_events": args.print_events,
            "skip_cpp_build": args.skip_cpp_build,
            "continue_on_error": args.continue_on_error,
            "auto_start": args.auto_start,
        },
    }
    (experiment_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== Baseline Batch ===")
    baseline_records: List[Dict[str, object]] = []
    for idx in range(1, args.baseline_runs + 1):
        report_json = baseline_reports_dir / f"baseline_run_{idx:02d}.json"
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_openface_baseline.py"),
            "--device",
            str(args.device),
            "--out-dir",
            str(baseline_runs_dir),
            "--timeout-seconds",
            str(args.baseline_timeout_seconds),
            "--report-json",
            str(report_json),
        ]
        print(f"\n[baseline {idx}/{args.baseline_runs}] 摄像头基线采集中...")
        rc = _run_cmd(cmd, cwd=ROOT)
        rec = {"index": idx, "report_json": str(report_json), "return_code": rc, "status": "ok" if rc == 0 else "failed"}
        baseline_records.append(rec)
        if rc != 0 and not args.continue_on_error:
            summary = {
                "status": "failed",
                "stage": "baseline",
                "baseline_records": baseline_records,
            }
            (experiment_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            return rc

    baseline_aggregate_json = baseline_root / "baseline_aggregate.json"
    baseline_eval_rc: int | None = None
    baseline_csv_files = sorted(baseline_runs_dir.glob("webcam_*.csv"))
    if baseline_csv_files:
        cmd_eval_baseline = [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_openface_runs.py"),
            "--runs-dir",
            str(baseline_runs_dir),
            "--glob",
            "webcam_*.csv",
            "--report-json",
            str(baseline_aggregate_json),
        ]
        baseline_eval_rc = _run_cmd(cmd_eval_baseline, cwd=ROOT)
    else:
        print("[skip] baseline 聚合评估已跳过（未找到 webcam_*.csv）")

    print("\n=== Live End-to-End Batch ===")
    live_specs: List[LiveRunSpec] = []
    for backend in backends:
        repeats = args.python_repeats if backend == "python" else args.cpp_repeats
        if repeats <= 0:
            continue
        for task in tasks:
            tid = task.get("task_id", "")
            target = task.get("target_text", "")
            for rep in range(1, repeats + 1):
                live_specs.append(LiveRunSpec(backend=backend, task_id=tid, target_text=target, repeat_index=rep))

    live_records: List[Dict[str, object]] = []
    center_map = _build_target_center_map(candidate_slots=8) if args.execution_mode == "headless_replay" else {}
    for idx, spec in enumerate(live_specs, start=1):
        run_id = spec.run_id
        print("\n" + "=" * 72)
        print(f"[{idx}/{len(live_specs)}] backend={spec.backend} task={spec.task_id} repeat={spec.repeat_index}")
        print(f"目标句：{spec.target_text}")
        if args.execution_mode == "live":
            print("请在运行窗口完成对应输入任务（建议先标定并保持坐姿稳定）。")
        else:
            print("headless_replay 模式：将自动生成注视轨迹并回放，无需图形界面人工操作。")

        if args.execution_mode == "live" and (not args.auto_start):
            try:
                input("准备好后按 Enter 开始该轮采集...")
            except KeyboardInterrupt:
                print("\n用户中断。")
                break

        openface_out_dir = live_openface_dir / run_id
        synthetic_gaze_csv = live_synthetic_gaze_dir / f"{run_id}_gaze.csv"
        session_log = live_logs_dir / f"{run_id}.jsonl"
        pipeline_report = live_pipeline_reports_dir / f"{run_id}_pipeline.json"
        eval_report = live_eval_reports_dir / f"{run_id}_eval.json"
        env_overrides = {"OPENAI_API_KEY": ""} if args.force_heuristic_reranker else None

        plan_ids: List[str] | None = None
        plan_meta: Dict[str, object] | None = None
        if args.execution_mode == "live":
            cmd_live = [
                sys.executable,
                str(ROOT / "scripts" / "run_openface_live_pipeline.py"),
                "--device",
                str(args.device),
                "--runtime-backend",
                spec.backend,
                "--openface-out-dir",
                str(openface_out_dir),
                "--wait-csv-seconds",
                str(args.wait_csv_seconds),
                "--max-seconds",
                str(args.max_seconds),
                "--dwell-ms",
                str(args.dwell_ms),
                "--smoothing",
                args.smoothing,
                "--session-log",
                str(session_log),
                "--report-json",
                str(pipeline_report),
            ]

            if args.smoothing == "ema":
                cmd_live.extend(["--ema-alpha", str(args.ema_alpha)])
            elif args.smoothing == "one_euro":
                cmd_live.extend(
                    [
                        "--one-euro-min-cutoff",
                        str(args.one_euro_min_cutoff),
                        "--one-euro-beta",
                        str(args.one_euro_beta),
                        "--one-euro-d-cutoff",
                        str(args.one_euro_d_cutoff),
                    ]
                )

            if args.calibration_json is not None:
                cmd_live.extend(["--calibration-json", str(args.calibration_json)])
            if args.print_events:
                cmd_live.append("--print-events")
            if spec.backend == "cpp" and args.skip_cpp_build:
                cmd_live.append("--skip-cpp-build")

            rc_live = _run_cmd(cmd_live, cwd=ROOT, env_overrides=env_overrides)
        else:
            try:
                plan_ids = _headless_target_plan(task_id=spec.task_id, target_text=spec.target_text)
                plan_meta = _write_headless_gaze_csv(
                    csv_path=synthetic_gaze_csv,
                    target_ids=plan_ids,
                    center_map=center_map,
                    dwell_ms=args.dwell_ms,
                    step_ms=args.headless_step_ms,
                )
            except Exception as exc:
                rc_live = 2
                plan_meta = {"error": str(exc)}
            else:
                cmd_live = [
                    sys.executable,
                    str(ROOT / "scripts" / "run_gaze_pipeline.py"),
                    "--gaze-csv",
                    str(synthetic_gaze_csv),
                    "--runtime-backend",
                    spec.backend,
                    "--dwell-ms",
                    str(args.dwell_ms),
                    "--smoothing",
                    args.smoothing,
                    "--candidate-slots",
                    "8",
                    "--session-log",
                    str(session_log),
                    "--report-json",
                    str(pipeline_report),
                ]
                if args.smoothing == "ema":
                    cmd_live.extend(["--ema-alpha", str(args.ema_alpha)])
                elif args.smoothing == "one_euro":
                    cmd_live.extend(
                        [
                            "--one-euro-min-cutoff",
                            str(args.one_euro_min_cutoff),
                            "--one-euro-beta",
                            str(args.one_euro_beta),
                            "--one-euro-d-cutoff",
                            str(args.one_euro_d_cutoff),
                        ]
                    )
                # Synthetic gaze is already normalized to [0,1], so do not pass calibration-json.
                if spec.backend == "cpp" and args.skip_cpp_build:
                    cmd_live.append("--skip-cpp-build")
                rc_live = _run_cmd(cmd_live, cwd=ROOT, env_overrides=env_overrides)

        record: Dict[str, object] = {
            "run_id": run_id,
            "execution_mode": args.execution_mode,
            "backend": spec.backend,
            "task_id": spec.task_id,
            "target_text": spec.target_text,
            "repeat_index": spec.repeat_index,
            "openface_out_dir": str(openface_out_dir),
            "synthetic_gaze_csv": str(synthetic_gaze_csv) if args.execution_mode == "headless_replay" else None,
            "headless_plan_target_ids": plan_ids if plan_ids is not None else None,
            "headless_plan_meta": plan_meta,
            "session_log": str(session_log),
            "pipeline_report": str(pipeline_report),
            "eval_report": str(eval_report),
            "live_return_code": rc_live,
            "status": "ok" if rc_live == 0 else "failed",
        }

        if rc_live == 0:
            cmd_eval = [
                sys.executable,
                str(ROOT / "scripts" / "evaluate_keyboard_task.py"),
                "--session-log",
                str(session_log),
                "--target-text",
                spec.target_text,
                "--report-json",
                str(eval_report),
            ]
            rc_eval = _run_cmd(cmd_eval, cwd=ROOT)
            record["eval_return_code"] = rc_eval
            if rc_eval == 0:
                record["metrics"] = _extract_single_eval_metrics(eval_report)
            else:
                record["status"] = "failed"
                record["metrics"] = {
                    "ok": False,
                    "error": "evaluate_keyboard_task failed",
                }
        else:
            record["metrics"] = {
                "ok": False,
                "error": "run_openface_live_pipeline failed",
            }

        live_records.append(record)

        if record["status"] != "ok" and not args.continue_on_error:
            print("\n[stop] 检测到失败并且未启用 --continue-on-error，提前结束批量实验。")
            break

    baseline_aggregate = None
    if baseline_aggregate_json.exists():
        baseline_aggregate = json.loads(baseline_aggregate_json.read_text(encoding="utf-8"))

    summary = {
        "status": "ok",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "experiment_root": str(experiment_root),
        "baseline": {
            "records": baseline_records,
            "aggregate_return_code": baseline_eval_rc,
            "aggregate_report": str(baseline_aggregate_json),
            "aggregate": baseline_aggregate,
        },
        "live": {
            "planned_run_count": len(live_specs),
            "executed_run_count": len(live_records),
            "records": live_records,
            "aggregate": _aggregate_live(live_records),
        },
    }

    summary_path = experiment_root / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Batch Finished ===")
    print(f"实验目录: {experiment_root}")
    print(f"总汇总:   {summary_path}")

    overall = (summary.get("live", {}).get("aggregate", {}).get("overall", {}))
    print(
        "Live总体: run_count={run_count}, exact_match_rate={rate}, mean_cer={cer}, mean_cpm={cpm}".format(
            run_count=overall.get("run_count"),
            rate=overall.get("exact_match_rate"),
            cer=overall.get("mean_cer"),
            cpm=overall.get("mean_cpm"),
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
