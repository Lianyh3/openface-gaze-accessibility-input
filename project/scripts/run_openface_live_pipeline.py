#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.candidate_pool import build_default_provider
from gaze_mvp.calibration import load_affine_calibration
from gaze_mvp.dwell_detector import DwellDetector
from gaze_mvp.gaze_hit_test import LayoutPreset, build_default_hit_tester
from gaze_mvp.gaze_runtime_pipeline import GazeKeyboardRuntime, GazePointObservation, LinearNormalizer
from gaze_mvp.gaze_smoothing import EmaSmoother2D, OneEuroSmoother2D
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow, SessionLogger
from gaze_mvp.keyboard_mvp import KeyboardMVP
from gaze_mvp.llm_factory import build_reranker_from_config
from gaze_mvp.openface_runner import build_openface_command

WORKSPACE_ROOT = ROOT.parent
DEFAULT_OPENFACE_BIN = WORKSPACE_ROOT / "OpenFace-OpenFace_2.2.0" / "build_clean" / "bin" / "FeatureExtraction"
DEFAULT_MODEL_LOC = (
    WORKSPACE_ROOT / "OpenFace-OpenFace_2.2.0" / "build_clean" / "bin" / "model" / "main_clnf_wild.txt"
)
DEFAULT_RUNS_DIR = ROOT / "data" / "runs"


class GrowingOpenFaceCsvSource:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self._last_row_count = 0

    def _read_all_rows(self) -> List[dict]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            try:
                raw_headers = next(reader)
            except StopIteration:
                return []
            headers = [h.strip() for h in raw_headers]
            rows: List[dict] = []
            for raw_row in reader:
                row = {headers[i]: raw_row[i].strip() if i < len(raw_row) else "" for i in range(len(headers))}
                rows.append(row)
        return rows

    def read_new_rows(self) -> List[dict]:
        rows = self._read_all_rows()
        if len(rows) < self._last_row_count:
            self._last_row_count = 0
        new_rows = rows[self._last_row_count :]
        self._last_row_count = len(rows)
        return new_rows


def _default_session_log_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return ROOT / "data" / "logs" / f"gaze_live_session_{stamp}.jsonl"


def _default_out_dir() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return DEFAULT_RUNS_DIR / f"openface_live_{stamp}"


def _resolve_latest_csv(out_dir: Path) -> Path | None:
    csv_files = sorted(out_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csv_files:
        return None
    return csv_files[0]


def _tail_lines(path: Path, line_count: int = 30) -> List[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-line_count:]


def _headless_hint(return_code: int) -> str:
    if return_code != -6:
        return ""
    if os.environ.get("DISPLAY"):
        return ""
    return (
        "OpenFace webcam mode needs a GUI window (press q to stop), but DISPLAY is empty.\n"
        "Run this command in VM desktop terminal, or enable X11 forwarding first."
    )


def _merge_runtime_result(
    acc: Dict[str, object],
    partial: Dict[str, object],
) -> None:
    acc["point_count"] = int(acc["point_count"]) + int(partial["point_count"])
    acc["mapped_point_count"] = int(acc["mapped_point_count"]) + int(partial["mapped_point_count"])
    acc["unmapped_point_count"] = int(acc["unmapped_point_count"]) + int(partial["unmapped_point_count"])
    acc["emitted_count"] = int(acc["emitted_count"]) + int(partial["emitted_count"])
    acc["dispatch_error_count"] = int(acc["dispatch_error_count"]) + int(partial["dispatch_error_count"])
    for target_id, count in partial["target_hit_counts"].items():
        hit_counts = acc["target_hit_counts"]
        assert isinstance(hit_counts, dict)
        hit_counts[target_id] = int(hit_counts.get(target_id, 0)) + int(count)
    emitted = acc["emitted"]
    assert isinstance(emitted, list)
    emitted.extend(partial["emitted"])
    dispatch_errors = acc["dispatch_errors"]
    assert isinstance(dispatch_errors, list)
    dispatch_errors.extend(partial["dispatch_errors"])
    acc["final_state"] = partial["final_state"]


def _stop_process(proc: subprocess.Popen[str], timeout_seconds: float = 5.0) -> int:
    if proc.poll() is not None:
        return int(proc.returncode)
    proc.terminate()
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2.0)
    return int(proc.returncode)


def _parse_point(
    row: dict,
    timestamp_col: str,
    x_col: str,
    y_col: str,
    timestamp_scale: float,
    fallback_fps: float,
    last_ts_ms: int,
) -> tuple[GazePointObservation | None, int]:
    x_raw = str(row.get(x_col, "")).strip()
    y_raw = str(row.get(y_col, "")).strip()
    if not x_raw or not y_raw:
        return None, last_ts_ms

    try:
        gaze_x = float(x_raw)
        gaze_y = float(y_raw)
    except ValueError:
        return None, last_ts_ms

    if not math.isfinite(gaze_x) or not math.isfinite(gaze_y):
        return None, last_ts_ms

    ts_raw = str(row.get(timestamp_col, "")).strip()
    if ts_raw:
        try:
            timestamp_ms = int(float(ts_raw) * timestamp_scale)
        except ValueError:
            timestamp_ms = last_ts_ms + int(round(1000.0 / fallback_fps))
    else:
        timestamp_ms = last_ts_ms + int(round(1000.0 / fallback_fps))

    if timestamp_ms <= last_ts_ms:
        timestamp_ms = last_ts_ms + 1

    point = GazePointObservation(timestamp_ms=timestamp_ms, gaze_x=gaze_x, gaze_y=gaze_y)
    return point, timestamp_ms


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run OpenFace webcam live and drive gaze->hit-test->dwell->keyboard pipeline."
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "default.json")
    parser.add_argument("--openface-bin", type=Path, default=DEFAULT_OPENFACE_BIN)
    parser.add_argument("--model-loc", type=Path, default=DEFAULT_MODEL_LOC)
    parser.add_argument("--device", type=int, default=0, help="Webcam device index.")
    parser.add_argument(
        "--openface-out-dir",
        type=Path,
        default=None,
        help="OpenFace output directory. Default: timestamped under data/runs.",
    )
    parser.add_argument(
        "--wait-csv-seconds",
        type=float,
        default=20.0,
        help="Max seconds to wait for OpenFace CSV generation.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Optional force stop after N seconds.",
    )
    parser.add_argument("--poll-interval-ms", type=int, default=40)
    parser.add_argument("--timestamp-col", type=str, default="timestamp")
    parser.add_argument("--x-col", type=str, default="gaze_angle_x")
    parser.add_argument("--y-col", type=str, default="gaze_angle_y")
    parser.add_argument(
        "--timestamp-scale",
        type=float,
        default=1000.0,
        help="Scale timestamp into ms. OpenFace timestamp is seconds, so default is 1000.",
    )
    parser.add_argument(
        "--fallback-fps",
        type=float,
        default=20.0,
        help="Fallback timestamp step used when timestamp column is empty.",
    )
    parser.add_argument("--dwell-ms", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=8)
    parser.add_argument("--candidate-slots", type=int, default=8)
    parser.add_argument("--calibration-json", type=Path, default=None)
    parser.add_argument("--smoothing", choices=("none", "ema", "one_euro"), default="none")
    parser.add_argument("--ema-alpha", type=float, default=0.4)
    parser.add_argument("--one-euro-min-cutoff", type=float, default=1.0)
    parser.add_argument("--one-euro-beta", type=float, default=0.01)
    parser.add_argument("--one-euro-d-cutoff", type=float, default=1.0)
    parser.add_argument("--x-min", type=float, default=-0.6)
    parser.add_argument("--x-max", type=float, default=0.6)
    parser.add_argument("--y-min", type=float, default=-0.6)
    parser.add_argument("--y-max", type=float, default=0.6)
    parser.add_argument("--no-clamp", action="store_true")
    parser.add_argument("--print-events", action="store_true", help="Print every emitted keyboard event.")
    parser.add_argument(
        "--export-gaze-csv",
        type=Path,
        default=None,
        help="Optional path to export parsed live gaze rows (timestamp_ms,gaze_x,gaze_y).",
    )
    parser.add_argument("--session-log", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.openface_bin.exists():
        raise SystemExit(f"FeatureExtraction not found: {args.openface_bin}")
    if not args.model_loc.exists():
        raise SystemExit(f"OpenFace model not found: {args.model_loc}")
    if args.calibration_json is not None and not args.calibration_json.exists():
        raise SystemExit(f"Calibration JSON not found: {args.calibration_json}")
    if args.wait_csv_seconds <= 0:
        raise SystemExit("--wait-csv-seconds must be positive.")
    if args.poll_interval_ms <= 0:
        raise SystemExit("--poll-interval-ms must be positive.")
    if args.fallback_fps <= 0:
        raise SystemExit("--fallback-fps must be positive.")

    config, reranker = build_reranker_from_config(args.config)
    dwell_ms = args.dwell_ms if args.dwell_ms is not None else config.dwell_ms

    keyboard = KeyboardMVP(reranker=reranker)
    session_log = args.session_log if args.session_log is not None else _default_session_log_path()
    flow = KeyboardEventFlow(
        keyboard=keyboard,
        candidate_provider=build_default_provider(),
        session_logger=SessionLogger(session_log),
        candidate_limit=args.candidate_limit,
    )

    hit_tester = build_default_hit_tester(LayoutPreset(candidate_slots=args.candidate_slots))
    detector = DwellDetector(dwell_ms=dwell_ms)
    if args.calibration_json is not None:
        normalizer = load_affine_calibration(args.calibration_json)
        normalization_detail = {
            "mode": "affine_calibration",
            "calibration_json": str(args.calibration_json),
            "model": normalizer.to_dict(),
        }
    else:
        normalizer = LinearNormalizer(
            x_min=args.x_min,
            x_max=args.x_max,
            y_min=args.y_min,
            y_max=args.y_max,
            clamp=not args.no_clamp,
        )
        normalization_detail = {
            "mode": "linear_minmax",
            "x_min": args.x_min,
            "x_max": args.x_max,
            "y_min": args.y_min,
            "y_max": args.y_max,
            "clamp": not args.no_clamp,
        }

    if args.smoothing == "none":
        smoother = None
        smoothing_detail = {"mode": "none"}
    elif args.smoothing == "ema":
        smoother = EmaSmoother2D(alpha=args.ema_alpha)
        smoothing_detail = {"mode": "ema", "ema_alpha": args.ema_alpha}
    else:
        smoother = OneEuroSmoother2D(
            min_cutoff=args.one_euro_min_cutoff,
            beta=args.one_euro_beta,
            d_cutoff=args.one_euro_d_cutoff,
        )
        smoothing_detail = {
            "mode": "one_euro",
            "min_cutoff": args.one_euro_min_cutoff,
            "beta": args.one_euro_beta,
            "d_cutoff": args.one_euro_d_cutoff,
        }

    runtime = GazeKeyboardRuntime(
        hit_tester=hit_tester,
        dwell_detector=detector,
        event_flow=flow,
        normalizer=normalizer,
        smoother=smoother,
    )

    out_dir = args.openface_out_dir if args.openface_out_dir is not None else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    openface_log = out_dir / "openface_stdout.log"
    openface_cmd = build_openface_command(
        openface_bin=args.openface_bin,
        model_loc=args.model_loc,
        out_dir=out_dir,
        device=args.device,
    )

    with openface_log.open("w", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(
            openface_cmd,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            text=True,
        )

    csv_path: Path | None = None
    wait_start = time.monotonic()
    while time.monotonic() - wait_start < args.wait_csv_seconds:
        csv_path = _resolve_latest_csv(out_dir)
        if csv_path is not None:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if csv_path is None:
        return_code = _stop_process(proc)
        tail = _tail_lines(openface_log)
        detail = "\n".join(tail) if tail else "(no OpenFace logs)"
        hint = _headless_hint(return_code)
        if hint:
            raise SystemExit(
                f"OpenFace exited before CSV generation (code={return_code}).\n{hint}\nOpenFace log tail:\n{detail}"
            )
        raise SystemExit(
            f"OpenFace did not produce CSV in time (code={return_code}, wait={args.wait_csv_seconds}s).\n"
            f"OpenFace log tail:\n{detail}"
        )

    source = GrowingOpenFaceCsvSource(csv_path=csv_path)
    agg_result: Dict[str, object] = {
        "point_count": 0,
        "mapped_point_count": 0,
        "unmapped_point_count": 0,
        "target_hit_counts": {},
        "emitted_count": 0,
        "emitted": [],
        "dispatch_error_count": 0,
        "dispatch_errors": [],
        "final_state": flow.keyboard.get_state().to_dict(),
    }
    row_count = 0
    skipped_rows = 0
    last_timestamp_ms = int(time.time() * 1000)
    started = time.monotonic()
    stopped_by_max_seconds = False

    gaze_export_fp = None
    gaze_export_writer = None
    if args.export_gaze_csv is not None:
        args.export_gaze_csv.parent.mkdir(parents=True, exist_ok=True)
        gaze_export_fp = args.export_gaze_csv.open("w", encoding="utf-8", newline="")
        gaze_export_writer = csv.DictWriter(gaze_export_fp, fieldnames=["timestamp_ms", "gaze_x", "gaze_y"])
        gaze_export_writer.writeheader()

    try:
        while True:
            rows = source.read_new_rows()
            for row in rows:
                row_count += 1
                point, last_timestamp_ms = _parse_point(
                    row=row,
                    timestamp_col=args.timestamp_col,
                    x_col=args.x_col,
                    y_col=args.y_col,
                    timestamp_scale=args.timestamp_scale,
                    fallback_fps=args.fallback_fps,
                    last_ts_ms=last_timestamp_ms,
                )
                if point is None:
                    skipped_rows += 1
                    continue

                if gaze_export_writer is not None:
                    gaze_export_writer.writerow(
                        {
                            "timestamp_ms": point.timestamp_ms,
                            "gaze_x": point.gaze_x,
                            "gaze_y": point.gaze_y,
                        }
                    )

                partial = runtime.process([point])
                _merge_runtime_result(agg_result, partial)

                if args.print_events and partial["emitted_count"] > 0:
                    for item in partial["emitted"]:
                        print(
                            json.dumps(
                                {
                                    "timestamp_ms": item["timestamp_ms"],
                                    "target_id": item["target_id"],
                                    "event": item["event"],
                                },
                                ensure_ascii=False,
                            )
                        )

            if args.max_seconds is not None and (time.monotonic() - started) >= args.max_seconds:
                stopped_by_max_seconds = True
                _stop_process(proc)
                break

            if proc.poll() is not None:
                # Flush any trailing rows that appeared right before process exit.
                trailing_rows = source.read_new_rows()
                for row in trailing_rows:
                    row_count += 1
                    point, last_timestamp_ms = _parse_point(
                        row=row,
                        timestamp_col=args.timestamp_col,
                        x_col=args.x_col,
                        y_col=args.y_col,
                        timestamp_scale=args.timestamp_scale,
                        fallback_fps=args.fallback_fps,
                        last_ts_ms=last_timestamp_ms,
                    )
                    if point is None:
                        skipped_rows += 1
                        continue
                    if gaze_export_writer is not None:
                        gaze_export_writer.writerow(
                            {
                                "timestamp_ms": point.timestamp_ms,
                                "gaze_x": point.gaze_x,
                                "gaze_y": point.gaze_y,
                            }
                        )
                    partial = runtime.process([point])
                    _merge_runtime_result(agg_result, partial)
                break

            time.sleep(max(0.01, args.poll_interval_ms / 1000.0))
    finally:
        if gaze_export_fp is not None:
            gaze_export_fp.close()

    return_code = proc.poll()
    if return_code is None:
        return_code = _stop_process(proc)

    output = {
        "config_path": str(args.config),
        "llm": {
            "provider": config.llm.provider,
            "api_style": config.llm.api_style,
            "model": config.llm.model,
        },
        "openface": {
            "openface_bin": str(args.openface_bin),
            "model_loc": str(args.model_loc),
            "device": args.device,
            "command": openface_cmd,
            "out_dir": str(out_dir),
            "csv_path": str(csv_path),
            "stdout_log": str(openface_log),
            "return_code": int(return_code),
            "stopped_by_max_seconds": stopped_by_max_seconds,
            "max_seconds": args.max_seconds,
        },
        "stream": {
            "timestamp_col": args.timestamp_col,
            "x_col": args.x_col,
            "y_col": args.y_col,
            "timestamp_scale": args.timestamp_scale,
            "poll_interval_ms": args.poll_interval_ms,
            "rows_read": row_count,
            "rows_skipped_invalid": skipped_rows,
            "export_gaze_csv": str(args.export_gaze_csv) if args.export_gaze_csv is not None else None,
        },
        "dwell_ms": dwell_ms,
        "candidate_limit": args.candidate_limit,
        "candidate_slots": args.candidate_slots,
        "normalization": normalization_detail,
        "smoothing": smoothing_detail,
        "session_log": str(session_log),
        "layout": hit_tester.layout_summary(),
        "result": agg_result,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")

    if int(return_code) not in (0, -15, 143) and not stopped_by_max_seconds:
        tail = _tail_lines(openface_log)
        detail = "\n".join(tail) if tail else "(no OpenFace logs)"
        raise SystemExit(f"OpenFace exited with non-zero code {return_code}.\nOpenFace log tail:\n{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
