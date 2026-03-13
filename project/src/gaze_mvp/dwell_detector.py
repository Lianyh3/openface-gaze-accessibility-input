from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class GazeObservation:
    timestamp_ms: int
    target_id: str


@dataclass(frozen=True)
class DwellEmission:
    kind: str
    payload: Dict[str, object]
    target_id: str
    dwell_started_ms: int
    dwell_elapsed_ms: int
    emitted_at_ms: int

    def to_metrics(self) -> Dict[str, object]:
        return {
            "trigger_source": "dwell",
            "target_id": self.target_id,
            "dwell_started_ms": self.dwell_started_ms,
            "dwell_elapsed_ms": self.dwell_elapsed_ms,
            "emitted_at_ms": self.emitted_at_ms,
        }


def parse_target_to_event(target_id: str) -> Tuple[str, Dict[str, object]] | None:
    """
    Convert a hit-tested gaze target into keyboard event kind + payload.
    Expected target formats:
    - key:<text>            -> key_input
    - cand:<index>          -> candidate_pick
    - action:back|commit|clear|refresh
    """

    token = target_id.strip()
    if not token:
        return None

    if token.startswith("key:"):
        text = token.split(":", 1)[1]
        if not text:
            return None
        return "key_input", {"text": text}

    if token.startswith("cand:"):
        raw = token.split(":", 1)[1].strip()
        if not raw.isdigit():
            return None
        return "candidate_pick", {"index": int(raw)}

    if token.startswith("action:"):
        action = token.split(":", 1)[1].strip().lower()
        mapping = {
            "back": "backspace",
            "commit": "commit_direct",
            "clear": "clear",
            "refresh": "candidate_refresh",
        }
        event_kind = mapping.get(action)
        if event_kind is None:
            return None
        return event_kind, {}

    return None


class DwellDetector:
    def __init__(self, dwell_ms: int):
        if dwell_ms <= 0:
            raise ValueError("dwell_ms must be positive.")
        self.dwell_ms = dwell_ms
        self._active_target: Optional[str] = None
        self._target_start_ms: Optional[int] = None
        self._emitted_for_active = False

    def reset(self) -> None:
        self._active_target = None
        self._target_start_ms = None
        self._emitted_for_active = False

    def update(self, obs: GazeObservation) -> DwellEmission | None:
        target_id = obs.target_id.strip()
        if not target_id:
            self.reset()
            return None

        if target_id != self._active_target:
            self._active_target = target_id
            self._target_start_ms = obs.timestamp_ms
            self._emitted_for_active = False
            return None

        if self._emitted_for_active:
            return None

        assert self._target_start_ms is not None
        elapsed = obs.timestamp_ms - self._target_start_ms
        if elapsed < self.dwell_ms:
            return None

        event = parse_target_to_event(target_id)
        self._emitted_for_active = True
        if event is None:
            return None
        kind, payload = event
        return DwellEmission(
            kind=kind,
            payload=payload,
            target_id=target_id,
            dwell_started_ms=self._target_start_ms,
            dwell_elapsed_ms=elapsed,
            emitted_at_ms=obs.timestamp_ms,
        )
