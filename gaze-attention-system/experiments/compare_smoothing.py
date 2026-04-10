"""平滑算法离线对比（最小可运行版）。

用途：
- 读取一份 OpenFace CSV（包含 gaze_angle_x/y、timestamp）
- 对比 none / ema / one_euro 三种平滑方法
- 输出抖动指标（标准差）与简单延迟近似指标

运行：
  python experiments/compare_smoothing.py --csv data/runtime/gaze_output.csv
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.gaze_input.smoothing import GazeSmoother


def read_series(csv_path: Path):
    t, x, y = [], [], []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = float(row["timestamp"])
                gx = float(row["gaze_angle_x"])
                gy = float(row["gaze_angle_y"])
            except Exception:
                continue
            t.append(ts)
            x.append(gx)
            y.append(gy)
    return np.array(t), np.array(x), np.array(y)


def smooth_series(method: str, t: np.ndarray, x: np.ndarray, y: np.ndarray):
    smoother = GazeSmoother(method=method)
    sx, sy = [], []
    for ts, gx, gy in zip(t, x, y):
        vx, vy = smoother.smooth(float(gx), float(gy), float(ts))
        sx.append(vx)
        sy.append(vy)
    return np.array(sx), np.array(sy)


def estimate_delay(raw: np.ndarray, smoothed: np.ndarray) -> float:
    """简单延迟近似：最大互相关位置对应的样本偏移。"""
    if len(raw) < 10:
        return 0.0
    a = raw - np.mean(raw)
    b = smoothed - np.mean(smoothed)
    corr = np.correlate(a, b, mode="full")
    lag = int(np.argmax(corr) - (len(raw) - 1))
    return float(abs(lag))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True, help="OpenFace 输出 CSV 路径")
    args = ap.parse_args()

    if not args.csv.exists():
        raise FileNotFoundError(f"CSV 不存在: {args.csv}")

    t, x, y = read_series(args.csv)
    if len(t) < 20:
        raise RuntimeError("CSV 数据太少，至少需要 20 帧")

    methods = ["none", "ema", "one_euro"]
    print("method,jitter_std_x,jitter_std_y,delay_samples_x,delay_samples_y")

    for m in methods:
        sx, sy = smooth_series(m, t, x, y)
        jitter_x = float(np.std(sx))
        jitter_y = float(np.std(sy))
        delay_x = estimate_delay(x, sx)
        delay_y = estimate_delay(y, sy)
        print(f"{m},{jitter_x:.6f},{jitter_y:.6f},{delay_x:.1f},{delay_y:.1f}")


if __name__ == "__main__":
    main()
