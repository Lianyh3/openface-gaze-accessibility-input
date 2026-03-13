#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/lyh/workspace"
PROJECT="$ROOT/project"

usage() {
  cat <<'EOF'
Unified project runner

Usage:
  bash /home/lyh/workspace/run.sh <command> [args...]

Commands:
  cam        Run OpenFace webcam baseline capture
  eval       Evaluate captured webcam CSV runs
  keyboard   Start keyboard MVP CLI
  summary    Summarize latest keyboard session logs
  task-eval  Evaluate keyboard text task (CER/CPM/WPM)
  rerank     Run candidate rerank demo
  dwell      Replay dwell target timeline
  gaze       Run gaze->hit-test->dwell->keyboard pipeline
  gaze-live  Run OpenFace live webcam + gaze runtime pipeline
  calib      Fit 9-point affine calibration from sample CSV
  calib-collect  Collect online 9-point calibration points from growing CSV
  help       Show this help message

Examples:
  bash /home/lyh/workspace/run.sh cam
  bash /home/lyh/workspace/run.sh eval
  bash /home/lyh/workspace/run.sh keyboard
  bash /home/lyh/workspace/run.sh task-eval "我今天想去图书馆"
  bash /home/lyh/workspace/run.sh rerank "我今天想去" "图书馆,食堂,实验室,操场"
  bash /home/lyh/workspace/run.sh gaze --report-json /tmp/gaze_report.json
  bash /home/lyh/workspace/run.sh gaze --smoothing one_euro --one-euro-beta 0.01
  bash /home/lyh/workspace/run.sh gaze-live --max-seconds 20 --print-events
  bash /home/lyh/workspace/run.sh calib --output-json /tmp/calib.json
  bash /home/lyh/workspace/run.sh calib-collect --source-csv /tmp/live_gaze.csv --auto-start
EOF
}

cmd="${1:-help}"

case "$cmd" in
  help|-h|--help)
    usage
    ;;
  cam)
    shift
    python3 "$PROJECT/scripts/run_openface_baseline.py" \
      --device 0 \
      --out-dir "$PROJECT/data/runs/check_cam_defaults" \
      --report-json "$PROJECT/data/reports/check_cam_defaults_report.json" \
      "$@"
    ;;
  eval)
    shift
    python3 "$PROJECT/scripts/evaluate_openface_runs.py" \
      --runs-dir "$PROJECT/data/runs/check_cam_defaults" \
      --report-json "$PROJECT/data/reports/check_cam_batch_eval.json" \
      "$@"
    ;;
  keyboard)
    shift
    python3 "$PROJECT/scripts/run_keyboard_mvp.py" "$@"
    ;;
  summary)
    shift
    python3 "$PROJECT/scripts/summarize_keyboard_session.py" "$@"
    ;;
  task-eval)
    shift
    if [[ $# -eq 0 ]]; then
      python3 "$PROJECT/scripts/evaluate_keyboard_task.py" \
        --tasks-csv "$PROJECT/data/samples/fixed_text_tasks_v1.csv" \
        --task-id "T01" \
        --report-json "$PROJECT/data/reports/keyboard_task_latest_report.json"
    elif [[ "${1:-}" == --* ]]; then
      python3 "$PROJECT/scripts/evaluate_keyboard_task.py" "$@"
    else
      target="${1}"
      shift
      python3 "$PROJECT/scripts/evaluate_keyboard_task.py" \
        --target-text "$target" \
        --report-json "$PROJECT/data/reports/keyboard_task_latest_report.json" \
        "$@"
    fi
    ;;
  rerank)
    shift
    if [[ $# -eq 0 ]]; then
      python3 "$PROJECT/scripts/demo_candidate_rerank.py" \
        --prefix "我今天想去" \
        --candidates "图书馆,食堂,实验室,操场"
    elif [[ "${1:-}" == --* ]]; then
      python3 "$PROJECT/scripts/demo_candidate_rerank.py" "$@"
    else
      prefix="${1:-我今天想去}"
      candidates="${2:-图书馆,食堂,实验室,操场}"
      if [[ $# -ge 1 ]]; then shift; fi
      if [[ $# -ge 1 ]]; then shift; fi
      python3 "$PROJECT/scripts/demo_candidate_rerank.py" \
        --prefix "$prefix" \
        --candidates "$candidates" \
        "$@"
    fi
    ;;
  dwell)
    shift
    python3 "$PROJECT/scripts/replay_dwell_targets.py" \
      --targets-csv "$PROJECT/data/samples/dwell_targets_demo.csv" \
      "$@"
    ;;
  gaze)
    shift
    python3 "$PROJECT/scripts/run_gaze_pipeline.py" \
      --gaze-csv "$PROJECT/data/samples/gaze_points_demo.csv" \
      "$@"
    ;;
  gaze-live)
    shift
    python3 "$PROJECT/scripts/run_openface_live_pipeline.py" \
      --device 0 \
      --report-json "$PROJECT/data/reports/gaze_live_latest_report.json" \
      "$@"
    ;;
  calib)
    shift
    python3 "$PROJECT/scripts/fit_9point_calibration.py" \
      --points-csv "$PROJECT/data/samples/calibration_points_9_demo.csv" \
      "$@"
    ;;
  calib-collect)
    shift
    python3 "$PROJECT/scripts/collect_9point_calibration.py" "$@"
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac
