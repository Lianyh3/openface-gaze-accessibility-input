from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PromptBuilder:
    top_k: int = 5

    def build(self, prefix: str, context_text: str = "") -> str:
        context = context_text.strip()
        return (
            "你是眼控输入法的候选词补全器。"
            "请基于前缀和上下文输出最可能的短词或短语。"
            f"仅返回 {self.top_k} 个候选，按可能性从高到低排列。"
            "输出必须是 JSON 数组字符串，不要输出解释。\n"
            f"前缀: {prefix}\n"
            f"上下文: {context}"
        )
