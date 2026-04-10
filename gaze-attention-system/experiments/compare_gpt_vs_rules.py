"""GPT 与规则引擎对比（最小可运行版）。

用途：
- 读取 OpenFace CSV，提取窗口特征
- 同时调用规则引擎与 GPT
- 输出两路标签分布与 GPT 基本开销

运行：
  python experiments/compare_gpt_vs_rules.py --csv data/runtime/gaze_output.csv
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
from src.gaze_input.gpt_analyzer import GptAnalyzer


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--step", type=int, default=10, help="每隔多少帧评估一次窗口")
    args = ap.parse_args()

    frames = read_frames(args.csv)
    if len(frames) < 20:
        raise RuntimeError("有效帧太少")

    extractor = FeatureExtractor(window_size_sec=2.0, min_valid_ratio=0.7)
    rules = RuleEngine()
    gpt = GptAnalyzer(fallback_engine=rules)

    rule_counts = {k: 0 for k in AttentionLabel}
    gpt_counts = {k: 0 for k in AttentionLabel}

    total = 0
    total_tokens = 0
    latencies = []

    for i, fr in enumerate(frames):
        extractor.push(fr)
        if i % max(1, args.step) != 0:
            continue
        feat = extractor.extract()
        if feat is None:
            continue

        total += 1
        lb_rule, _ = rules.judge(feat)
        lb_gpt, _, _ = gpt.judge(feat)

        rule_counts[lb_rule] += 1
        gpt_counts[lb_gpt] += 1
        total_tokens += gpt.last_tokens
        latencies.append(gpt.last_latency_ms)

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print(f"total_windows={total}")
    print("rules:")
    for k, v in rule_counts.items():
        if v:
            print(f"  {k.value}: {v}")

    print("gpt:")
    for k, v in gpt_counts.items():
        if v:
            print(f"  {k.value}: {v}")

    print(f"gpt_avg_latency_ms={avg_latency:.1f}")
    print(f"gpt_total_tokens={total_tokens}")


if __name__ == "__main__":
    main()
