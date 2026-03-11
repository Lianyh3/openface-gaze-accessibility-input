#!/usr/bin/env bash
set -euo pipefail

python3 /home/lyh/workspace/project/scripts/fit_9point_calibration.py \
  --points-csv /home/lyh/workspace/project/data/samples/calibration_points_9_demo.csv \
  "$@"
