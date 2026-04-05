#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gaze_mvp.candidate_pool import build_default_provider
from gaze_mvp.keyboard_event_flow import KeyboardEventFlow, SessionLogger
from gaze_mvp.keyboard_mvp import KeyboardMVP
from gaze_mvp.llm_factory import build_reranker_from_config


def _print_state(state: dict) -> None:
    print(json.dumps(state, ensure_ascii=False, indent=2))


def _usage() -> str:
    return (
        "Commands:\n"
        "  status                        Show current keyboard state\n"
        "  dwell_key <text>              Emit a key-input dwell event\n"
        "  dwell_pick <index>            Emit a candidate-pick dwell event\n"
        "  dwell_back                    Emit a backspace dwell event\n"
        "  dwell_commit                  Emit a direct-commit dwell event\n"
        "  dwell_clear                   Emit a clear dwell event\n"
        "  refresh                       Refresh candidates from candidate provider\n"
        "  cand <c1,c2,c3>               Optional manual candidate override (debug)\n"
        "  quit                          Exit\n"
        "Aliases: type/pick/back/commit/clear map to corresponding dwell_* events.\n"
    )


def _default_session_log_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return ROOT / "data" / "logs" / f"keyboard_session_{stamp}.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Keyboard MVP CLI with OpenAI candidate reranking.")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "default.json",
        help="Path to config JSON.",
    )
    parser.add_argument(
        "--session-log",
        type=Path,
        default=None,
        help="Path to jsonl session log. Default: auto timestamp under data/logs.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=8,
        help="Max number of candidates kept in current ranking.",
    )
    args = parser.parse_args()

    config, reranker = build_reranker_from_config(args.config)
    keyboard = KeyboardMVP(reranker=reranker)
    candidate_provider = build_default_provider()
    session_log = args.session_log if args.session_log is not None else _default_session_log_path()
    flow = KeyboardEventFlow(
        keyboard=keyboard,
        candidate_provider=candidate_provider,
        session_logger=SessionLogger(session_log),
        candidate_limit=args.candidate_limit,
    )

    print("[keyboard-mvp] started")
    print(f"[llm] provider={config.llm.provider} style={config.llm.api_style} model={config.llm.model}")
    print(f"[session-log] {session_log}")
    print(_usage(), end="")

    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue

        parts = shlex.split(line)
        command = parts[0].lower()
        arg = line[len(parts[0]) :].strip()
        cli_metrics = {"trigger_source": "manual_cli", "command": command}

        try:
            if command == "quit":
                break
            if command == "help":
                print(_usage(), end="")
                continue
            if command == "status":
                state, _ = flow.dispatch(kind="status", metrics=cli_metrics)
                _print_state(state.to_dict())
            elif command in ("dwell_key", "type"):
                state, _ = flow.dispatch(kind="key_input", payload={"text": arg}, metrics=cli_metrics)
                _print_state(state.to_dict())
            elif command == "cand":
                candidates = [c.strip() for c in arg.split(",") if c.strip()]
                state, _ = flow.dispatch(
                    kind="manual_candidates",
                    payload={"candidates": candidates},
                    metrics=cli_metrics,
                )
                _print_state(state.to_dict())
            elif command in ("dwell_pick", "pick"):
                index = int(arg)
                state, _ = flow.dispatch(kind="candidate_pick", payload={"index": index}, metrics=cli_metrics)
                _print_state(state.to_dict())
            elif command in ("dwell_back", "back"):
                state, _ = flow.dispatch(kind="backspace", metrics=cli_metrics)
                _print_state(state.to_dict())
            elif command in ("dwell_commit", "commit"):
                state, _ = flow.dispatch(kind="commit_direct", metrics=cli_metrics)
                _print_state(state.to_dict())
            elif command in ("dwell_clear", "clear"):
                state, _ = flow.dispatch(kind="clear", metrics=cli_metrics)
                _print_state(state.to_dict())
            elif command == "refresh":
                state, _ = flow.dispatch(kind="candidate_refresh", metrics=cli_metrics)
                _print_state(state.to_dict())
            else:
                print(f"Unknown command: {command}")
                print(_usage(), end="")
        except Exception as exc:  # keep CLI alive for quick manual demos
            print(f"[error] {exc}")

    print("[keyboard-mvp] bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
