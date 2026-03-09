from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


class OpenFaceRunError(RuntimeError):
    """Raised when OpenFace execution fails."""


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
) -> subprocess.CompletedProcess[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_openface_command(
        openface_bin=openface_bin,
        model_loc=model_loc,
        out_dir=out_dir,
        input_image=input_image,
        input_video=input_video,
        device=device,
    )

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if proc.returncode != 0:
        raise OpenFaceRunError(f"OpenFace failed with code {proc.returncode}\n{proc.stdout}")
    return proc

