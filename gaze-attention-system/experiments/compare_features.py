"""特征方案对比（最小可运行版）。

用途：
- 读取 OpenFace CSV
- 以滑动窗口提取特征
- 对比：仅注视特征 vs 多特征融合（规则引擎）

运行：
  python experiments/compare_features.py --csv data/runtime/gaze_output.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.gaze_input.csv_parser import FrameData
from src.gaze_input.feature_extractor import FeatureExtractor
from src.gaze_input.label_schema import AttentionLabel
from src.gaze_input.rule_engine import RuleEngine


def read_frames(csv_path: Path) -> list[FrameData]:
    frames: list[FrameData] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                conf = float(row["confidence"])
                succ = int(float(row["success"]))
                if conf < 0.7 or succ == 0:
                    continue
                frames.append(
                    FrameData(
                        frame=int(float(row["frame"])),
                        timestamp=float(row["timestamp"]),
                        confidence=conf,
                        success=bool(succ),
                        gaze_angle_x=float(row["gaze_angle_x"]),
                        gaze_angle_y=float(row["gaze_angle_y"]),
                        pose_Rx=float(row["pose_Rx"]),
                        pose_Ry=float(row["pose_Ry"]),
                        pose_Rz=float(row["pose_Rz"]),
                        au45=float(row.get("AU45_r", 0.0)),
                    )
                )
            except Exception:
                continue
    return frames


def judge_gaze_only(gaze_dev_mean: float) -> AttentionLabel:
    if gaze_dev_mean > 0.3:
        return AttentionLabel.SEVERELY_DISTRACTED
    if gaze_dev_mean > 0.15:
        return AttentionLabel.DISTRACTED
    return AttentionLabel.FOCUSED


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    args = ap.parse_args()

    frames = read_frames(args.csv)
    if len(frames) < 20:
        raise RuntimeError("有效帧太少")

    extractor = FeatureExtractor(window_size_sec=2.0, min_valid_ratio=0.7)
    engine = RuleEngine()

    total = 0
    gaze_only_counts = {k: 0 for k in AttentionLabel}
    fused_counts = {k: 0 for k in AttentionLabel}

    for fr in frames:
        extractor.push(fr)
        feat = extractor.extract()
        if feat is None:
            continue
        total += 1

        lb1 = judge_gaze_only(feat.gaze_deviation_mean)
        lb2, _ = engine.judge(feat)
        gaze_only_counts[lb1] += 1
        fused_counts[lb2] += 1

    print(f"total_windows={total}")
    print("gaze_only:")
    for k, v in gaze_only_counts.items():
        if v:
            print(f"  {k.value}: {v}")

    print("fused_features:")
    for k, v in fused_counts.items():
        if v:
            print(f"  {k.value}: {v}")


if __name__ == "__main__":
    main()
