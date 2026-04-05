from __future__ import annotations

from dataclasses import dataclass

from gaze_keyboard.common.contracts import DwellEvent


@dataclass(slots=True)
class DwellStateMachine:
    fire_ms: int = 700
    cancel_ms: int = 250

    _active_target: str | None = None
    _enter_ts: int | None = None
    _last_seen_ts: int | None = None
    _fired: bool = False

    def update(self, timestamp_ms: int, target_id: str | None) -> list[DwellEvent]:
        events: list[DwellEvent] = []

        if target_id is None:
            if self._active_target is not None and self._last_seen_ts is not None and self._enter_ts is not None:
                gap = timestamp_ms - self._last_seen_ts
                if gap >= self.cancel_ms:
                    duration = max(0, self._last_seen_ts - self._enter_ts)
                    events.append(
                        DwellEvent(
                            timestamp_ms=timestamp_ms,
                            target_id=self._active_target,
                            state="cancel",
                            duration_ms=duration,
                        )
                    )
                    self._reset()
            return events

        if self._active_target is None:
            self._active_target = target_id
            self._enter_ts = timestamp_ms
            self._last_seen_ts = timestamp_ms
            self._fired = False
            events.append(
                DwellEvent(
                    timestamp_ms=timestamp_ms,
                    target_id=target_id,
                    state="enter",
                    duration_ms=0,
                )
            )
            return events

        if target_id != self._active_target:
            if self._enter_ts is not None:
                duration = max(0, timestamp_ms - self._enter_ts)
                events.append(
                    DwellEvent(
                        timestamp_ms=timestamp_ms,
                        target_id=self._active_target,
                        state="cancel",
                        duration_ms=duration,
                    )
                )
            self._active_target = target_id
            self._enter_ts = timestamp_ms
            self._last_seen_ts = timestamp_ms
            self._fired = False
            events.append(
                DwellEvent(
                    timestamp_ms=timestamp_ms,
                    target_id=target_id,
                    state="enter",
                    duration_ms=0,
                )
            )
            return events

        self._last_seen_ts = timestamp_ms
        duration = 0 if self._enter_ts is None else max(0, timestamp_ms - self._enter_ts)
        events.append(
            DwellEvent(
                timestamp_ms=timestamp_ms,
                target_id=target_id,
                state="stay",
                duration_ms=duration,
            )
        )

        if not self._fired and duration >= self.fire_ms:
            self._fired = True
            events.append(
                DwellEvent(
                    timestamp_ms=timestamp_ms,
                    target_id=target_id,
                    state="fire",
                    duration_ms=duration,
                )
            )

        return events

    def _reset(self) -> None:
        self._active_target = None
        self._enter_ts = None
        self._last_seen_ts = None
        self._fired = False
