from __future__ import annotations

from pathlib import Path

from gaze_keyboard.system.runtime import GazeKeyboardRuntime

MOCK_HEADER = "frame,timestamp,confidence,gaze_0_x,gaze_0_y,gaze_0_z,pose_Rx,pose_Ry,pose_Rz\n"


def build_mock_csv(path: Path, frames: int = 20) -> None:
    rows: list[str] = [MOCK_HEADER]
    for i in range(frames):
        timestamp = i * 0.05
        rows.append(f"{i + 1},{timestamp:.3f},0.95,-0.85,0.00,0.00,0,0,0\n")
    path.write_text("".join(rows), encoding="utf-8")


def main() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = logs_dir / "smoke_runtime_openface_stream.csv"
    build_mock_csv(csv_path)

    runtime = GazeKeyboardRuntime(
        csv_path=csv_path,
        poll_ms=40,
        min_confidence=0.6,
        dwell_ms=700,
        session_id="smoke-runtime",
        log_dir=logs_dir,
    )
    runtime.run(max_iterations=1)

    assert runtime.input_controller.text == "A", (
        "Expected runtime text='A', got "
        f"{runtime.input_controller.text!r}"
    )
    print("[OK] runtime smoke passed. text='A'")


if __name__ == "__main__":
    main()
