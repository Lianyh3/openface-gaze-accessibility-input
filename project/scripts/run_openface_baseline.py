#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.baseline_metrics import compute_baseline_metrics
from gaze_mvp.csv_schema import load_openface_csv, validate_required_columns
from gaze_mvp.openface_runner import OpenFaceRunError, run_openface

WORKSPACE_ROOT = ROOT.parent
DEFAULT_OPENFACE_BIN = WORKSPACE_ROOT / "OpenFace-OpenFace_2.2.0" / "build_clean" / "bin" / "FeatureExtraction"
DEFAULT_MODEL_LOC = (
    WORKSPACE_ROOT / "OpenFace-OpenFace_2.2.0" / "build_clean" / "bin" / "model" / "main_clnf_wild.txt"
)
DEFAULT_RUNS_DIR = ROOT / "data" / "runs"


def _pick_first_csv(out_dir: Path) -> Path:
    csv_files = sorted(out_dir.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not csv_files:
        raise FileNotFoundError(f"No CSV generated under: {out_dir}")
    return csv_files[0]


def _resolve_with_default(value: Path | None, default: Path) -> Path:
    return value if value is not None else default


def _fail_if_missing(path: Path, argument_name: str) -> None:
    if not path.exists():
        raise SystemExit(
            f"Path not found for {argument_name}: {path}\n"
            f"Please set a valid path with --{argument_name.replace('_', '-')}."
        )


def _default_out_dir() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return DEFAULT_RUNS_DIR / f"openface_run_{stamp}"


def _camera_hint(stdout: str) -> str:
    if "Failed to open the webcam" not in stdout and "can't open camera by index" not in stdout:
        return ""
    return (
        "Camera open failed. Try these checks:\n"
        "1) Confirm device index: rerun with --device 1 (or other index).\n"
        "2) Check whether other apps occupy /dev/video0 (Teams/Zoom/browser).\n"
        "3) Verify user belongs to video group and re-login after changes."
    )


def _headless_hint(error_text: str, using_webcam: bool) -> str:
    if not using_webcam:
        return ""
    if "code -6" not in error_text and "forcing visualization of tracking" not in error_text:
        return ""
    if os.environ.get("DISPLAY"):
        return ""
    return (
        "OpenFace webcam mode needs a GUI window (press q to stop), but DISPLAY is empty.\n"
        "Run this command in the VM desktop terminal (not remote SSH), or enable X11 forwarding first."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpenFace and summarize baseline CSV metrics.")
    parser.add_argument(
        "--openface-bin",
        type=Path,
        default=None,
        help=f"Path to FeatureExtraction binary (default: {DEFAULT_OPENFACE_BIN}).",
    )
    parser.add_argument(
        "--model-loc",
        type=Path,
        default=None,
        help=f"Path to main_clnf_wild.txt (default: {DEFAULT_MODEL_LOC}).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for OpenFace artifacts. Defaults to a timestamped run dir.",
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input-image", type=Path, default=None)
    input_group.add_argument("--input-video", type=Path, default=None)
    input_group.add_argument("--device", type=int, default=None)

    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    openface_bin = _resolve_with_default(args.openface_bin, DEFAULT_OPENFACE_BIN)
    model_loc = _resolve_with_default(args.model_loc, DEFAULT_MODEL_LOC)
    out_dir = args.out_dir if args.out_dir is not None else _default_out_dir()

    _fail_if_missing(openface_bin, "openface_bin")
    _fail_if_missing(model_loc, "model_loc")

    try:
        proc = run_openface(
            openface_bin=openface_bin,
            model_loc=model_loc,
            out_dir=out_dir,
            input_image=args.input_image,
            input_video=args.input_video,
            device=args.device,
            timeout_seconds=args.timeout_seconds,
        )
    except OpenFaceRunError as exc:
        hint = _headless_hint(str(exc), using_webcam=args.device is not None)
        if hint:
            raise SystemExit(f"{exc}\n{hint}") from exc
        raise

    try:
        csv_path = _pick_first_csv(out_dir)
    except FileNotFoundError as exc:
        stdout_tail = "\n".join(proc.stdout.splitlines()[-40:])
        hint = _camera_hint(proc.stdout)
        detail = f"{exc}\nOpenFace output tail:\n{stdout_tail}"
        if hint:
            detail = f"{detail}\n{hint}"
        raise SystemExit(detail) from exc
    data = load_openface_csv(csv_path)
    schema = validate_required_columns(data.headers)
    metrics = compute_baseline_metrics(data.rows).to_dict()

    report = {
        "openface_bin": str(openface_bin),
        "model_loc": str(model_loc),
        "out_dir": str(out_dir),
        "command_stdout_tail": proc.stdout.splitlines()[-30:],
        "csv_path": str(csv_path),
        "row_count": len(data.rows),
        "required_columns": schema,
        "metrics": metrics,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
