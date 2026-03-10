#!/usr/bin/env bash
set -euo pipefail

python3 /home/lyh/workspace/project/scripts/run_gaze_pipeline.py \
  --gaze-csv /home/lyh/workspace/project/data/samples/gaze_points_demo.csv \
  "$@"
