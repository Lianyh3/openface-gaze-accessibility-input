#!/usr/bin/env bash
set -euo pipefail

python3 /home/lyh/workspace/project/scripts/replay_dwell_targets.py \
  --targets-csv /home/lyh/workspace/project/data/samples/dwell_targets_demo.csv \
  "$@"
