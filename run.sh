#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/lyh/workspace"
PROJECT="$ROOT/project"

run_with_virtual_display_if_needed() {
  # Prefer xvfb when available (stable for headless/remote sessions),
  # unless the user explicitly requests real display rendering.
  if command -v xvfb-run >/dev/null 2>&1 && [[ "${PREFER_REAL_DISPLAY:-0}" != "1" ]]; then
    xvfb-run -a "$@"
    return $?
  fi

  if [[ -n "${DISPLAY:-}" ]]; then
    "$@"
    return $?
  fi

  echo "DISPLAY is empty and xvfb-run is not installed." >&2
  echo "Install xvfb or run in an environment with X11 display." >&2
  return 2
}

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
  m0-check   Validate M0 C++/Python runtime interface contract
  m1-check   Check M1 C++ core alignment (normalizer/hit-test/dwell)
  m2-check   Check M2 C++ core alignment (calibration/smoothing)
  rerank     Run candidate rerank demo
  dwell      Replay dwell target timeline
  gaze       Run gaze->hit-test->dwell->keyboard pipeline
  gaze-cpp   Run C++ replay backend (M1) -> Python keyboard event flow
  backend-compare  Compare Python/C++ gaze runtime backends
  gaze-live  Run OpenFace live webcam + gaze runtime pipeline
  calib      Fit 9-point affine calibration from sample CSV
  calib-collect  Collect online 9-point calibration points from growing CSV
  e2e-batch  Batch end-to-end experiment runner (baseline + live + auto eval)
  help       Show this help message

Examples:
  bash /home/lyh/workspace/run.sh cam
  bash /home/lyh/workspace/run.sh eval
  bash /home/lyh/workspace/run.sh keyboard
  bash /home/lyh/workspace/run.sh task-eval "我今天想去图书馆"
  bash /home/lyh/workspace/run.sh m0-check
  bash /home/lyh/workspace/run.sh m1-check
  bash /home/lyh/workspace/run.sh m2-check
  bash /home/lyh/workspace/run.sh rerank "我今天想去" "图书馆,食堂,实验室,操场"
  bash /home/lyh/workspace/run.sh gaze --report-json /tmp/gaze_report.json
  bash /home/lyh/workspace/run.sh gaze-cpp --report-json /tmp/gaze_cpp_report.json
  bash /home/lyh/workspace/run.sh backend-compare --report-json /tmp/runtime_backend_compare.json
  bash /home/lyh/workspace/run.sh gaze --smoothing one_euro --one-euro-beta 0.01
  bash /home/lyh/workspace/run.sh gaze-live --max-seconds 20 --print-events
  bash /home/lyh/workspace/run.sh gaze-live --runtime-backend cpp --max-seconds 20
  bash /home/lyh/workspace/run.sh calib --output-json /tmp/calib.json
  bash /home/lyh/workspace/run.sh calib-collect --source-csv /tmp/live_gaze.csv --auto-start
  bash /home/lyh/workspace/run.sh e2e-batch --task-ids T01,T02 --python-repeats 2 --cpp-repeats 1
  bash /home/lyh/workspace/run.sh e2e-batch --execution-mode headless_replay --task-ids T01,T02 --python-repeats 2 --cpp-repeats 1 --force-heuristic-reranker
EOF
}

cmd="${1:-help}"

case "$cmd" in
  help|-h|--help)
    usage
    ;;
  cam)
    shift
    run_with_virtual_display_if_needed \
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
  m0-check)
    shift
    python3 "$PROJECT/scripts/check_m0_contract.py" \
      --report-json "$PROJECT/data/reports/m0_contract_check_report.json" \
      "$@"
    ;;
  m1-check)
    shift
    python3 "$PROJECT/scripts/check_m1_alignment.py" \
      --report-json "$PROJECT/data/reports/m1_alignment_check_report.json" \
      "$@"
    ;;
  m2-check)
    shift
    python3 "$PROJECT/scripts/check_m2_alignment.py" \
      --report-json "$PROJECT/data/reports/m2_alignment_check_report.json" \
      "$@"
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
  gaze-cpp)
    shift
    python3 "$PROJECT/scripts/run_gaze_cpp_pipeline.py" \
      --gaze-csv "$PROJECT/data/samples/gaze_points_demo.csv" \
      "$@"
    ;;
  backend-compare)
    shift
    python3 "$PROJECT/scripts/compare_runtime_backends.py" \
      --gaze-csv "$PROJECT/data/samples/gaze_points_demo.csv" \
      --report-json "$PROJECT/data/reports/runtime_backend_compare_latest.json" \
      --force-heuristic-reranker \
      "$@"
    ;;
  gaze-live)
    shift
    run_with_virtual_display_if_needed \
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
  e2e-batch)
    shift
    run_with_virtual_display_if_needed \
      python3 "$PROJECT/scripts/run_end2end_batch.py" "$@"
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac
