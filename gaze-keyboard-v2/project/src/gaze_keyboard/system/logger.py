from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gaze_keyboard.common.contracts import CandidateSuggestion, DwellEvent, RawGazeSample, ScreenGazePoint


@dataclass(slots=True)
class SessionLogger:
    session_id: str
    log_dir: Path

    def __post_init__(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._raw_path = self.log_dir / f"{self.session_id}_raw_gaze.jsonl"
        self._runtime_path = self.log_dir / f"{self.session_id}_runtime_event.jsonl"
        self._ai_path = self.log_dir / f"{self.session_id}_ai_event.jsonl"
        self._summary_path = self.log_dir / f"{self.session_id}_summary.json"

    def log_raw_sample(self, sample: RawGazeSample) -> None:
        self._append_jsonl(self._raw_path, {"event_type": "raw_gaze", **asdict(sample)})

    def log_point(self, point: ScreenGazePoint) -> None:
        self._append_jsonl(self._runtime_path, {"event_type": "screen_point", **asdict(point)})

    def log_dwell_event(self, event: DwellEvent) -> None:
        self._append_jsonl(self._runtime_path, {"event_type": "dwell", **asdict(event)})

    def log_key_fire(self, timestamp_ms: int, key_id: str, text: str) -> None:
        self._append_jsonl(
            self._runtime_path,
            {
                "event_type": "key_fire",
                "timestamp_ms": timestamp_ms,
                "key_id": key_id,
                "text": text,
            },
        )

    def log_ai_suggestion(self, timestamp_ms: int, suggestion: CandidateSuggestion) -> None:
        payload = {
            "event_type": "candidate_suggestion",
            "timestamp_ms": timestamp_ms,
            **asdict(suggestion),
        }
        self._append_jsonl(self._ai_path, payload)

    def log_session_summary(self, payload: dict[str, Any]) -> None:
        with self._summary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
