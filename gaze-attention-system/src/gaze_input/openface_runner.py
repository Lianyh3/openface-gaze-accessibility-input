"""OpenFace 子进程生命周期管理。

启动 FeatureExtraction.exe，管理其生命周期，返回输出 CSV 路径。
"""

from __future__ import annotations

import subprocess
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)


class OpenFaceRunner:
    """管理 OpenFace FeatureExtraction 子进程。"""

    def __init__(
        self,
        bin_path: str,
        device: int = 0,
        output_dir: str = "./data/runtime",
        mloc: str | None = None,
    ):
        self.bin_path = Path(bin_path)
        self.device = device
        self.output_dir = Path(output_dir).resolve()
        self.mloc = Path(mloc) if mloc else None
        self._proc: subprocess.Popen | None = None
        self._csv_path: Path | None = None

        if not self.bin_path.exists():
            raise FileNotFoundError(f"OpenFace 二进制不存在: {self.bin_path}")
        if self.mloc is not None and not self.mloc.exists():
            raise FileNotFoundError(f"OpenFace mloc 模型路径不存在: {self.mloc}")

    def start(self) -> Path:
        """启动 OpenFace，返回输出 CSV 文件路径。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 清理上次运行残留（避免旧 CSV 干扰）
        stale_csv = self.output_dir / "gaze_output.csv"
        if stale_csv.exists():
            try:
                stale_csv.unlink()
            except Exception:
                pass

        csv_base = self.output_dir / "gaze_output"
        cmd = [
            str(self.bin_path),
            "-device", str(self.device),
            "-of", str(csv_base),
            # 只输出我们需要的特征，减少 CSV 体积
            "-2Dfp", "-3Dfp", "-pdmparams", "-pose", "-aus", "-gaze",
        ]
        if self.mloc is not None:
            cmd.extend(["-mloc", str(self.mloc)])

        log.info("启动 OpenFace: %s", " ".join(cmd))
        # 避免 stdout/stderr 管道阻塞：直接丢弃输出
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW  # Windows 下不弹黑窗

        log_path = self.output_dir / "openface_stderr.log"
        err_file = open(log_path, "w", encoding="utf-8", errors="ignore")

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=err_file,
            creationflags=creationflags,
            cwd=str(self.bin_path.parent),  # 关键：让 OpenFace 在自身目录启动，便于找到模型文件
        )

        self._csv_path = self.output_dir / "gaze_output.csv"

        # 等待 CSV 文件出现（首次加载模型可能较慢）
        for _ in range(200):  # 最多等 20 秒
            if self._csv_path.exists():
                log.info("CSV 文件已生成: %s", self._csv_path)
                err_file.close()
                return self._csv_path

            # 若进程提前退出，给出日志提示
            if self._proc.poll() is not None:
                err_file.close()
                err_msg = ""
                try:
                    err_msg = log_path.read_text(encoding="utf-8", errors="ignore")[-1000:]
                except Exception:
                    pass
                raise RuntimeError(
                    f"OpenFace 进程提前退出，exit_code={self._proc.returncode}。"
                    f"请检查: {log_path}\n"
                    f"最近错误输出:\n{err_msg}"
                )

            time.sleep(0.1)

        err_file.close()
        raise TimeoutError(
            f"OpenFace 启动超时，CSV 文件未生成。请检查日志: {log_path}"
        )

    @property
    def csv_path(self) -> Path | None:
        return self._csv_path

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self):
        """优雅关闭 OpenFace 子进程。"""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            log.info("OpenFace 已停止")
        self._proc = None

    def __del__(self):
        self.stop()
