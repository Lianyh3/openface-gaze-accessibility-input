"""评估指标计算。"""

from __future__ import annotations

from dataclasses import dataclass, field
from .label_schema import AttentionLabel


@dataclass
class MetricsAccumulator:
    """累积预测结果，计算准确率等指标。"""
    predictions: list[AttentionLabel] = field(default_factory=list)
    ground_truths: list[AttentionLabel] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    token_counts: list[int] = field(default_factory=list)

    def add(
        self,
        pred: AttentionLabel,
        truth: AttentionLabel | None = None,
        latency_ms: float = 0,
        tokens: int = 0,
    ):
        self.predictions.append(pred)
        if truth is not None:
            self.ground_truths.append(truth)
        self.latencies_ms.append(latency_ms)
        self.token_counts.append(tokens)

    def accuracy(self) -> float:
        if not self.ground_truths:
            return 0.0
        n = min(len(self.predictions), len(self.ground_truths))
        correct = sum(
            1 for p, g in zip(self.predictions[:n], self.ground_truths[:n]) if p == g
        )
        return correct / n

    def avg_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0

    def total_tokens(self) -> int:
        return sum(self.token_counts)

    def summary(self) -> dict:
        return {
            "total_predictions": len(self.predictions),
            "total_ground_truths": len(self.ground_truths),
            "accuracy": round(self.accuracy(), 4),
            "avg_latency_ms": round(self.avg_latency_ms(), 1),
            "total_tokens": self.total_tokens(),
        }
