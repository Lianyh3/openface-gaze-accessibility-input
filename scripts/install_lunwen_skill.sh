#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/skills/lunwen"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
DEST="$CODEX_HOME_DIR/skills/lunwen"

FORCE=0
LINK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    --link)
      LINK=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: bash scripts/install_lunwen_skill.sh [--force] [--link]" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$SRC/SKILL.md" ]]; then
  echo "Skill source not found: $SRC" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"

if [[ -e "$DEST" || -L "$DEST" ]]; then
  if [[ "$FORCE" -ne 1 ]]; then
    echo "Destination already exists: $DEST" >&2
    echo "Re-run with --force to overwrite." >&2
    exit 1
  fi
  if [[ -L "$DEST" ]]; then
    rm -f "$DEST"
  else
    find "$DEST" -mindepth 1 -delete 2>/dev/null || true
  fi
fi

if [[ "$LINK" -eq 1 ]]; then
  ln -s "$SRC" "$DEST"
else
  mkdir -p "$DEST"
  cp -a "$SRC/." "$DEST/"
fi

echo "Installed lunwen skill to: $DEST"
echo "Restart Codex to pick up new skills."
