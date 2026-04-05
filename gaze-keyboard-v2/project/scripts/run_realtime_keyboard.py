from __future__ import annotations

import argparse
from pathlib import Path

from gaze_keyboard.common.config import AiConfig
from gaze_keyboard.system.runtime import GazeKeyboardRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run realtime gaze keyboard scaffold")
    parser.add_argument("--csv", type=Path, required=True, help="Path to OpenFace CSV output")
    parser.add_argument("--poll-ms", type=int, default=40, help="CSV poll interval in ms")
    parser.add_argument("--max-iterations", type=int, default=0, help="Stop after N polls (0 = infinite)")
    parser.add_argument("--dwell-ms", type=int, default=700, help="Dwell fire threshold in ms")
    parser.add_argument("--min-confidence", type=float, default=0.6, help="Minimum sample confidence")

    parser.add_argument("--ai-enabled", action="store_true", help="Enable AI candidate suggestion")
    parser.add_argument("--ai-top-k", type=int, default=5, help="Top-K candidates")
    parser.add_argument("--ai-timeout-ms", type=int, default=1000, help="AI request timeout")
    parser.add_argument("--ai-min-prefix", type=int, default=2, help="Minimum prefix length for AI")
    parser.add_argument("--ai-model", type=str, default="gpt-5.3-codex", help="Model name")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    ai_cfg = AiConfig(
        enabled=args.ai_enabled,
        model=args.ai_model,
        timeout_ms=args.ai_timeout_ms,
        top_k=args.ai_top_k,
        min_prefix_chars=args.ai_min_prefix,
    )

    runtime = GazeKeyboardRuntime(
        csv_path=args.csv,
        poll_ms=args.poll_ms,
        min_confidence=args.min_confidence,
        dwell_ms=args.dwell_ms,
        session_id="manual-run",
        log_dir=Path("logs"),
        ai_config=ai_cfg,
    )
    runtime.run(max_iterations=args.max_iterations)


if __name__ == "__main__":
    main()
