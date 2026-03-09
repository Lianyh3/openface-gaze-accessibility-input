#!/usr/bin/env bash
set -euo pipefail

python3 /home/lyh/workspace/project/scripts/run_openface_baseline.py \
  --device 0 \
  --out-dir /home/lyh/workspace/project/data/runs/check_cam_defaults \
  --report-json /home/lyh/workspace/project/data/reports/check_cam_defaults_report.json
