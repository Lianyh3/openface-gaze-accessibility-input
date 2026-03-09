from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from gaze_mvp.candidate_pool import CandidateProvider
from gaze_mvp.keyboard_mvp import KeyboardMVP, KeyboardState


@dataclass
class DwellEvent:
    event_id: int
    kind: str
    payload: Dict[str, Any]
    timestamp_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: DwellEvent, before_state: KeyboardState, after_state: KeyboardState) -> None:
        record = {
            "event": event.to_dict(),
            "before": before_state.to_dict(),
            "after": after_state.to_dict(),
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")


class KeyboardEventFlow:
    """
    Event-driven wrapper around KeyboardMVP.
    Future gaze dwell integration should only emit events to this flow.
    """

    def __init__(
        self,
        keyboard: KeyboardMVP,
        candidate_provider: CandidateProvider,
        session_logger: SessionLogger | None = None,
        candidate_limit: int = 8,
    ):
        self.keyboard = keyboard
        self.candidate_provider = candidate_provider
        self.session_logger = session_logger
        self.candidate_limit = candidate_limit
        self._event_seq = 1

    def _new_event(self, kind: str, payload: Dict[str, Any] | None = None) -> DwellEvent:
        event = DwellEvent(
            event_id=self._event_seq,
            kind=kind,
            payload=(payload or {}),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        self._event_seq += 1
        return event

    def _refresh_candidates(self) -> KeyboardState:
        state = self.keyboard.get_state()
        candidates = self.candidate_provider.suggest(
            committed_text=state.committed_text,
            composing_buffer=state.composing_buffer,
            limit=self.candidate_limit,
        )
        return self.keyboard.set_base_candidates(candidates)

    def _log_if_enabled(self, event: DwellEvent, before: KeyboardState, after: KeyboardState) -> None:
        if self.session_logger is not None:
            self.session_logger.append(event=event, before_state=before, after_state=after)

    def dispatch(self, kind: str, payload: Dict[str, Any] | None = None) -> Tuple[KeyboardState, DwellEvent]:
        event = self._new_event(kind=kind, payload=payload)
        before_state = self.keyboard.get_state()

        if kind == "key_input":
            text = str((payload or {}).get("text", ""))
            self.keyboard.type_text(text)
            after_state = self._refresh_candidates()
        elif kind == "backspace":
            self.keyboard.backspace()
            after_state = self._refresh_candidates()
        elif kind == "candidate_refresh":
            after_state = self._refresh_candidates()
        elif kind == "candidate_pick":
            index = int((payload or {}).get("index", 0))
            ranked = before_state.ranked_candidates
            if index > 0 and index <= len(ranked):
                event.payload["picked_candidate"] = ranked[index - 1]
            after_state = self.keyboard.pick_candidate(index)
        elif kind == "manual_candidates":
            raw_candidates = (payload or {}).get("candidates", [])
            if not isinstance(raw_candidates, list):
                raise ValueError("manual_candidates payload must include a list field: candidates.")
            candidates = [str(item).strip() for item in raw_candidates if str(item).strip()]
            after_state = self.keyboard.set_base_candidates(candidates)
        elif kind == "commit_direct":
            after_state = self.keyboard.commit_buffer_directly()
        elif kind == "clear":
            after_state = self.keyboard.clear()
        elif kind == "status":
            after_state = self.keyboard.get_state()
        else:
            raise ValueError(f"Unsupported event kind: {kind}")

        self._log_if_enabled(event=event, before=before_state, after=after_state)
        return after_state, event
