"""GPT 大模型注意力判断 — 结构化输出 + 降级回退。"""

from __future__ import annotations

import json
import logging
import os
import time

from .label_schema import AttentionLabel
from .feature_extractor import FeatureWindow
from .prompt_schema import SYSTEM_PROMPT, USER_TEMPLATE, OUTPUT_KEYS, VALID_LABELS
from .rule_engine import RuleEngine

log = logging.getLogger(__name__)


class GptAnalyzer:
    """调用 OpenAI GPT 进行注意力判断。"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0,
        timeout: float = 5.0,
        fallback_engine: RuleEngine | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.fallback = fallback_engine or RuleEngine()

        api_key = os.environ.get(api_key_env, "")
        self._client = None
        if api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=api_key, timeout=timeout)
            except ImportError:
                log.warning("openai 包未安装，GPT 路径不可用")
        else:
            log.warning("未设置 %s，GPT 路径不可用", api_key_env)

        # 统计
        self.last_latency_ms: float = 0
        self.last_tokens: int = 0

    def judge(self, feat: FeatureWindow) -> tuple[AttentionLabel, str, float]:
        """返回 (标签, 原因, 置信度)。失败时降级到规则引擎。"""
        if self._client is None:
            label, reason = self.fallback.judge(feat)
            return label, reason + " [规则引擎降级]", 0.5

        user_msg = USER_TEMPLATE.format(
            window_sec=feat.window_end - feat.window_start,
            **feat.to_dict(),
        )

        try:
            t0 = time.perf_counter()
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            self.last_latency_ms = (time.perf_counter() - t0) * 1000
            self.last_tokens = resp.usage.total_tokens if resp.usage else 0

            raw = resp.choices[0].message.content or ""
            result = json.loads(raw)

            # 校验输出格式
            if not OUTPUT_KEYS.issubset(result.keys()):
                raise ValueError(f"缺少字段: {OUTPUT_KEYS - result.keys()}")
            if result["label"] not in VALID_LABELS:
                raise ValueError(f"无效标签: {result['label']}")

            label = AttentionLabel(result["label"])
            return label, result["reason"], float(result["confidence"])

        except Exception as e:
            log.warning("GPT 调用失败，降级到规则引擎: %s", e)
            label, reason = self.fallback.judge(feat)
            return label, reason + " [GPT失败降级]", 0.5
