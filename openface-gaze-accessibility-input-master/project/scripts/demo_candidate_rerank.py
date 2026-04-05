#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.llm_factory import build_reranker_from_config


def _split_candidates(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerank candidate words using OpenAI (with local fallback).")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "default.json",
        help="Path to config JSON.",
    )
    parser.add_argument("--prefix", type=str, required=True, help="Current committed text or prefix context.")
    parser.add_argument(
        "--candidates",
        type=str,
        required=True,
        help='Comma-separated candidate list, e.g. "你好,您好,你们好".',
    )
    args = parser.parse_args()

    _, reranker = build_reranker_from_config(args.config)
    result = reranker.rerank(prefix_text=args.prefix, candidates=_split_candidates(args.candidates))
    print(
        json.dumps(
            {
                "prefix": args.prefix,
                "ranked": result.ranked,
                "source": result.source,
                "debug_message": result.debug_message,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
