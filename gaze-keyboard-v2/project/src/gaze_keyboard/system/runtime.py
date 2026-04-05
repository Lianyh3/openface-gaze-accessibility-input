from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from gaze_keyboard.ai.candidate_engine import CandidateEngine
from gaze_keyboard.algo.calibrator import LinearCalibrator
from gaze_keyboard.algo.dwell_state_machine import DwellStateMachine
from gaze_keyboard.algo.openface_stream import OpenFaceCsvPoller
from gaze_keyboard.algo.smoother import EmaSmoother
from gaze_keyboard.common.config import AiConfig, OpenFaceCsvConfig
from gaze_keyboard.system.hit_tester import HitTester
from gaze_keyboard.system.input_controller import InputController
from gaze_keyboard.system.keyboard_layout import build_qwerty_layout
from gaze_keyboard.system.logger import SessionLogger


@dataclass(slots=True)
class RuntimeStats:
    polls: int = 0
    samples: int = 0
    fired: int = 0
    ai_requests: int = 0
    ai_non_empty: int = 0
    started_at_ms: int = 0
    ended_at_ms: int = 0


class GazeKeyboardRuntime:
    def __init__(
        self,
        csv_path: Path,
        poll_ms: int = 40,
        min_confidence: float = 0.6,
        dwell_ms: int = 700,
        session_id: str = "dev-session",
        log_dir: Path = Path("logs"),
        ai_config: AiConfig | None = None,
    ) -> None:
        cfg = OpenFaceCsvConfig(csv_path=csv_path, poll_interval_ms=poll_ms)
        self.poller = OpenFaceCsvPoller(cfg)

        self.calibrator = LinearCalibrator(min_confidence=min_confidence)
        self.smoother = EmaSmoother(alpha=0.35)
        self.dwell = DwellStateMachine(fire_ms=dwell_ms)
        self.hit_tester = HitTester(keys=build_qwerty_layout())
        self.input_controller = InputController()
        self.logger = SessionLogger(session_id=session_id, log_dir=log_dir)
        self.stats = RuntimeStats()

        self.ai_config = ai_config or AiConfig(enabled=False)
        self.candidate_engine = CandidateEngine(self.ai_config) if self.ai_config.enabled else None

    def run(self, max_iterations: int = 0) -> None:
        self.stats.started_at_ms = int(time.time() * 1000)

        for batch in self.poller.iter_forever():
            self.stats.polls += 1
            self.stats.samples += len(batch)

            fired_keys: list[str] = []
            for sample in batch:
                self.logger.log_raw_sample(sample)
                mapped = self.calibrator.map_sample(sample)
                smoothed = self.smoother.update(mapped)
                self.logger.log_point(smoothed)

                target_id = self.hit_tester.locate(smoothed)
                events = self.dwell.update(smoothed.timestamp_ms, target_id)
                for event in events:
                    self.logger.log_dwell_event(event)
                    if event.state == "fire":
                        self.input_controller.apply_key(event.target_id)
                        self.logger.log_key_fire(
                            timestamp_ms=event.timestamp_ms,
                            key_id=event.target_id,
                            text=self.input_controller.text,
                        )
                        fired_keys.append(event.target_id)
                        self.stats.fired += 1

                        self._maybe_suggest_candidates(event.timestamp_ms)

            self._print_tick(fired_keys, len(batch))

            if max_iterations > 0 and self.stats.polls >= max_iterations:
                break

        self.stats.ended_at_ms = int(time.time() * 1000)
        self._write_summary()

    def _maybe_suggest_candidates(self, timestamp_ms: int) -> None:
        if self.candidate_engine is None:
            return

        text = self.input_controller.text
        prefix = text.split(" ")[-1] if text else ""
        self.stats.ai_requests += 1

        suggestion = self.candidate_engine.suggest(prefix=prefix, context_text=text)
        if suggestion.candidates:
            self.stats.ai_non_empty += 1

        self.logger.log_ai_suggestion(timestamp_ms=timestamp_ms, suggestion=suggestion)

    def _write_summary(self) -> None:
        duration_ms = max(0, self.stats.ended_at_ms - self.stats.started_at_ms)
        payload = {
            "polls": self.stats.polls,
            "samples": self.stats.samples,
            "fired": self.stats.fired,
            "final_text": self.input_controller.text,
            "duration_ms": duration_ms,
            "ai_requests": self.stats.ai_requests,
            "ai_non_empty": self.stats.ai_non_empty,
        }
        self.logger.log_session_summary(payload)

    def _print_tick(self, fired_keys: list[str], sample_count: int) -> None:
        poll = self.stats.polls
        text = self.input_controller.text
        if sample_count == 0:
            print(f"[poll {poll}] samples=0 text='{text}'")
            return

        if fired_keys:
            print(f"[poll {poll}] samples={sample_count} fired={fired_keys} text='{text}'")
        else:
            print(f"[poll {poll}] samples={sample_count} text='{text}'")
