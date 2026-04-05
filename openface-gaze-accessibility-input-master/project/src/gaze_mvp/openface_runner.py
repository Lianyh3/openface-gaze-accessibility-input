from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


class OpenFaceRunError(RuntimeError):
    """Raised when OpenFace execution fails."""


@dataclass
class OpenFaceRunResult:
    returncode: int
    stdout: str
    timed_out: bool


def build_openface_command(
    openface_bin: Path,
    model_loc: Path,
    out_dir: Path,
    input_image: Path | None = None,
    input_video: Path | None = None,
    device: int | None = None,
) -> List[str]:
    cmd = [str(openface_bin), "-mloc", str(model_loc), "-out_dir", str(out_dir)]

    selected = sum(x is not None for x in (input_image, input_video, device))
    if selected != 1:
        raise ValueError("Exactly one of input_image/input_video/device must be set.")

    if input_image is not None:
        cmd.extend(["-f", str(input_image)])
    elif input_video is not None:
        cmd.extend(["-f", str(input_video)])
    else:
        cmd.extend(["-device", str(device)])

    return cmd


def run_openface(
    openface_bin: Path,
    model_loc: Path,
    out_dir: Path,
    input_image: Path | None = None,
    input_video: Path | None = None,
    device: int | None = None,
    timeout_seconds: int | None = None,
) -> OpenFaceRunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_openface_command(
        openface_bin=openface_bin,
        model_loc=model_loc,
        out_dir=out_dir,
        input_image=input_image,
        input_video=input_video,
        device=device,
    )

    # Webcam mode is typically infinite until 'q' is pressed. If timeout_seconds
    # is set, treat timeout as a controlled stop instead of a hard failure.
    if timeout_seconds is not None:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        timed_out = False
        try:
            stdout, _ = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate()
        return_code = int(process.returncode)
    else:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        return_code = int(proc.returncode)
        stdout = proc.stdout
        timed_out = False

    if return_code != 0 and not timed_out:
        raise OpenFaceRunError(f"OpenFace failed with code {return_code}\n{stdout}")

    return OpenFaceRunResult(returncode=return_code, stdout=stdout, timed_out=timed_out)
