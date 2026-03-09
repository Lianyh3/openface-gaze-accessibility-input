#!/usr/bin/env bash
set -euo pipefail

python3 /home/lyh/workspace/project/scripts/evaluate_openface_runs.py \
  --runs-dir /home/lyh/workspace/project/data/runs/check_cam_defaults \
  --report-json /home/lyh/workspace/project/data/reports/check_cam_batch_eval.json
