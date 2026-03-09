#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-我今天想去}"
CANDIDATES="${2:-图书馆,食堂,实验室,操场}"

python3 /home/lyh/workspace/project/scripts/demo_candidate_rerank.py \
  --prefix "$PREFIX" \
  --candidates "$CANDIDATES"
