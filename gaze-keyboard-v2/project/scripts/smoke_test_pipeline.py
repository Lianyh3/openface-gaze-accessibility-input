from __future__ import annotations

from pathlib import Path

from gaze_keyboard.algo.calibrator import LinearCalibrator
from gaze_keyboard.algo.dwell_state_machine import DwellStateMachine
from gaze_keyboard.algo.openface_stream import OpenFaceCsvPoller
from gaze_keyboard.algo.smoother import EmaSmoother
from gaze_keyboard.common.config import OpenFaceCsvConfig
from gaze_keyboard.system.hit_tester import HitTester
from gaze_keyboard.system.input_controller import InputController
from gaze_keyboard.system.keyboard_layout import build_qwerty_layout


MOCK_HEADER = "frame,timestamp,confidence,gaze_0_x,gaze_0_y,gaze_0_z,pose_Rx,pose_Ry,pose_Rz\n"


def build_mock_csv(path: Path, frames: int = 20) -> None:
    rows: list[str] = [MOCK_HEADER]
    # gaze_0_x = -0.85 roughly maps near left keyboard region -> 'A'
    for i in range(frames):
        timestamp = i * 0.05
        rows.append(f"{i + 1},{timestamp:.3f},0.95,-0.85,0.00,0.00,0,0,0\n")
    path.write_text("".join(rows), encoding="utf-8")


def run_smoke(csv_path: Path) -> str:
    cfg = OpenFaceCsvConfig(csv_path=csv_path, poll_interval_ms=40)
    poller = OpenFaceCsvPoller(cfg)

    calibrator = LinearCalibrator(min_confidence=0.6)
    smoother = EmaSmoother(alpha=0.35)
    layout = build_qwerty_layout()
    hit_tester = HitTester(keys=layout)
    dwell = DwellStateMachine(fire_ms=700)
    controller = InputController()

    batch = poller.poll_once()
    for sample in batch:
        point = calibrator.map_sample(sample)
        smooth_point = smoother.update(point)
        target_id = hit_tester.locate(smooth_point)
        events = dwell.update(sample.timestamp_ms, target_id)
        for event in events:
            if event.state == "fire":
                controller.apply_key(event.target_id)

    return controller.text


def main() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = logs_dir / "smoke_openface_stream.csv"

    build_mock_csv(csv_path)
    text = run_smoke(csv_path)

    assert text == "A", f"Expected text='A', got text={text!r}"
    print("[OK] smoke pipeline passed. text='A'")


if __name__ == "__main__":
    main()
