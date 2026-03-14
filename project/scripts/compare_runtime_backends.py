#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.cpp_runtime_bridge import compile_m1_cpp



def _build_common_args(args: argparse.Namespace) -> List[str]:
    cmd = [
        "--config",
        str(args.config),
        "--gaze-csv",
        str(args.gaze_csv),
        "--timestamp-col",
        args.timestamp_col,
        "--x-col",
        args.x_col,
        "--y-col",
        args.y_col,
        "--candidate-limit",
        str(args.candidate_limit),
        "--candidate-slots",
        str(args.candidate_slots),
        "--smoothing",
        args.smoothing,
        "--ema-alpha",
        str(args.ema_alpha),
        "--one-euro-min-cutoff",
        str(args.one_euro_min_cutoff),
        "--one-euro-beta",
        str(args.one_euro_beta),
        "--one-euro-d-cutoff",
        str(args.one_euro_d_cutoff),
        "--x-min",
        str(args.x_min),
        "--x-max",
        str(args.x_max),
        "--y-min",
        str(args.y_min),
        "--y-max",
        str(args.y_max),
    ]
    if args.dwell_ms is not None:
        cmd.extend(["--dwell-ms", str(args.dwell_ms)])
    if args.calibration_json is not None:
        cmd.extend(["--calibration-json", str(args.calibration_json)])
    if args.no_clamp:
        cmd.append("--no-clamp")
    return cmd



def _load_api_key_env_name(config_path: Path) -> str | None:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    llm = payload.get("llm", {})
    if not isinstance(llm, dict):
        return None
    raw_name = llm.get("api_key_env")
    if raw_name is None:
        return None
    name = str(raw_name).strip()
    return name or None



def _normalize_emitted(items: object) -> List[Dict[str, object]]:
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        event = item.get("event", {})
        state = item.get("state", {})
        if not isinstance(event, dict):
            event = {}
        if not isinstance(state, dict):
            state = {}
        payload = event.get("payload", {})
        metrics = event.get("metrics", {})
        if not isinstance(payload, dict):
            payload = {}
        if not isinstance(metrics, dict):
            metrics = {}
        normalized.append(
            {
                "timestamp_ms": int(item.get("timestamp_ms", 0)),
                "target_id": str(item.get("target_id", "")),
                "kind": str(event.get("kind", "")),
                "payload": dict(sorted(payload.items())),
                "dwell_started_ms": int(metrics.get("dwell_started_ms", 0)),
                "dwell_elapsed_ms": int(metrics.get("dwell_elapsed_ms", 0)),
                "committed_text": str(state.get("committed_text", "")),
                "composing_buffer": str(state.get("composing_buffer", "")),
                "ranked_candidates": list(state.get("ranked_candidates", [])),
            }
        )
    return normalized



def _compare_reports(python_report: Dict[str, object], cpp_report: Dict[str, object]) -> Dict[str, object]:
    python_result = python_report.get("result", {})
    cpp_result = cpp_report.get("result", {})
    if not isinstance(python_result, dict):
        python_result = {}
    if not isinstance(cpp_result, dict):
        cpp_result = {}

    python_emitted = _normalize_emitted(python_result.get("emitted", []))
    cpp_emitted = _normalize_emitted(cpp_result.get("emitted", []))

    mismatch: List[Dict[str, object]] = []
    for index, (left, right) in enumerate(zip(python_emitted, cpp_emitted)):
        if left != right:
            mismatch.append({"index": index, "python": left, "cpp": right})
    if len(python_emitted) != len(cpp_emitted):
        mismatch.append(
            {
                "count_mismatch": {
                    "python_count": len(python_emitted),
                    "cpp_count": len(cpp_emitted),
                }
            }
        )

    final_state_match = python_result.get("final_state") == cpp_result.get("final_state")
    return {
        "python_emitted_count": len(python_emitted),
        "cpp_emitted_count": len(cpp_emitted),
        "mismatch_count": len(mismatch),
        "mismatch_preview": mismatch[:3],
        "final_state_match": final_state_match,
        "python_final_state": python_result.get("final_state", {}),
        "cpp_final_state": cpp_result.get("final_state", {}),
    }



def _summarize_timings(values_ms: List[float]) -> Dict[str, float | int]:
    return {
        "count": len(values_ms),
        "min_ms": min(values_ms),
        "max_ms": max(values_ms),
        "mean_ms": statistics.mean(values_ms),
        "median_ms": statistics.median(values_ms),
    }



def _run_backend(
    backend: str,
    base_args: List[str],
    work_dir: Path,
    env: Dict[str, str],
    cpp_binary: Path,
) -> Tuple[float, Dict[str, object], str]:
    report_path = work_dir / f"{backend}_report.json"
    session_log = work_dir / f"{backend}_session.jsonl"
    cmd = [sys.executable, str(ROOT / "scripts" / "run_gaze_pipeline.py")]
    cmd.extend(base_args)
    cmd.extend(["--runtime-backend", backend, "--session-log", str(session_log), "--report-json", str(report_path)])
    if backend == "cpp":
        cmd.extend(["--cpp-binary", str(cpp_binary), "--skip-cpp-build"])

    started = time.perf_counter()
    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return elapsed_ms, report, proc.stdout



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Python and C++ gaze runtime backends on the same gaze CSV."
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "default.json")
    parser.add_argument("--gaze-csv", type=Path, required=True)
    parser.add_argument("--timestamp-col", type=str, default="timestamp_ms")
    parser.add_argument("--x-col", type=str, default="gaze_x")
    parser.add_argument("--y-col", type=str, default="gaze_y")
    parser.add_argument("--dwell-ms", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=8)
    parser.add_argument("--candidate-slots", type=int, default=8)
    parser.add_argument("--calibration-json", type=Path, default=None)
    parser.add_argument("--smoothing", choices=("none", "ema", "one_euro"), default="none")
    parser.add_argument("--ema-alpha", type=float, default=0.4)
    parser.add_argument("--one-euro-min-cutoff", type=float, default=1.0)
    parser.add_argument("--one-euro-beta", type=float, default=0.01)
    parser.add_argument("--one-euro-d-cutoff", type=float, default=1.0)
    parser.add_argument("--x-min", type=float, default=0.0)
    parser.add_argument("--x-max", type=float, default=1.0)
    parser.add_argument("--y-min", type=float, default=0.0)
    parser.add_argument("--y-max", type=float, default=1.0)
    parser.add_argument("--no-clamp", action="store_true")
    parser.add_argument("--repeat", type=int, default=3, help="Timed repeat count for each backend.")
    parser.add_argument(
        "--cpp-binary",
        type=Path,
        default=Path("/tmp/gaze_m1_replay_compare"),
        help="Precompiled C++ binary path reused across timed runs.",
    )
    parser.add_argument(
        "--force-heuristic-reranker",
        action="store_true",
        help="Remove configured LLM API key env before running comparisons for deterministic fallback.",
    )
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.gaze_csv.exists():
        raise SystemExit(f"Gaze CSV not found: {args.gaze_csv}")
    if args.calibration_json is not None and not args.calibration_json.exists():
        raise SystemExit(f"Calibration JSON not found: {args.calibration_json}")
    if args.repeat <= 0:
        raise SystemExit("--repeat must be positive")

    base_args = _build_common_args(args)
    env = dict(os.environ)
    disabled_llm_env = None
    if args.force_heuristic_reranker:
        disabled_llm_env = _load_api_key_env_name(args.config)
        if disabled_llm_env:
            env.pop(disabled_llm_env, None)

    compile_m1_cpp(args.cpp_binary)

    python_times_ms: List[float] = []
    cpp_times_ms: List[float] = []
    last_python_report: Dict[str, object] = {}
    last_cpp_report: Dict[str, object] = {}

    with tempfile.TemporaryDirectory(prefix="runtime_backend_compare_") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        for run_index in range(args.repeat):
            run_dir = temp_dir / f"run_{run_index + 1}"
            run_dir.mkdir(parents=True, exist_ok=True)

            python_elapsed_ms, python_report, _ = _run_backend(
                backend="python",
                base_args=base_args,
                work_dir=run_dir,
                env=env,
                cpp_binary=args.cpp_binary,
            )
            cpp_elapsed_ms, cpp_report, _ = _run_backend(
                backend="cpp",
                base_args=base_args,
                work_dir=run_dir,
                env=env,
                cpp_binary=args.cpp_binary,
            )
            python_times_ms.append(python_elapsed_ms)
            cpp_times_ms.append(cpp_elapsed_ms)
            last_python_report = python_report
            last_cpp_report = cpp_report

    compare = _compare_reports(last_python_report, last_cpp_report)
    python_timing = _summarize_timings(python_times_ms)
    cpp_timing = _summarize_timings(cpp_times_ms)
    cpp_mean_ms = float(cpp_timing["mean_ms"])
    python_mean_ms = float(python_timing["mean_ms"])
    performance = {
        "python_mean_ms": python_mean_ms,
        "cpp_mean_ms": cpp_mean_ms,
        "mean_delta_ms": python_mean_ms - cpp_mean_ms,
        "speedup_ratio": (python_mean_ms / cpp_mean_ms) if cpp_mean_ms > 0 else None,
    }

    output = {
        "gaze_csv": str(args.gaze_csv),
        "config_path": str(args.config),
        "repeat": args.repeat,
        "runtime_backend_compare": compare,
        "python_timing": python_timing,
        "cpp_timing": cpp_timing,
        "performance": performance,
        "llm_control": {
            "force_heuristic_reranker": args.force_heuristic_reranker,
            "disabled_env_name": disabled_llm_env,
        },
        "python_result_preview": {
            "runtime_backend": last_python_report.get("runtime_backend", "python"),
            "result": last_python_report.get("result", {}),
        },
        "cpp_result_preview": {
            "runtime_backend": last_cpp_report.get("runtime_backend", "cpp"),
            "result": last_cpp_report.get("result", {}),
            "cpp_replay": last_cpp_report.get("cpp_replay", {}),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
