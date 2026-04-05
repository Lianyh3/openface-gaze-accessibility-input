from __future__ import annotations

import time
from dataclasses import dataclass, field

from gaze_keyboard.ai.codex_client import CodexClient
from gaze_keyboard.ai.prompt_builder import PromptBuilder
from gaze_keyboard.common.config import AiConfig
from gaze_keyboard.common.contracts import CandidateSuggestion


@dataclass(slots=True)
class CandidateEngine:
    config: AiConfig
    _cache: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.prompt_builder = PromptBuilder(top_k=self.config.top_k)
        self.client = CodexClient(self.config)

    def suggest(self, prefix: str, context_text: str = "") -> CandidateSuggestion:
        normalized = prefix.strip()
        if len(normalized) < self.config.min_prefix_chars:
            return CandidateSuggestion(prefix=normalized, candidates=[], latency_ms=0, source="fallback")

        if normalized in self._cache:
            return CandidateSuggestion(
                prefix=normalized,
                candidates=self._cache[normalized],
                latency_ms=0,
                source="cache",
            )

        prompt = self.prompt_builder.build(normalized, context_text=context_text)
        start = time.perf_counter()
        candidates, _, source = self.client.complete(prompt)
        latency_ms = int((time.perf_counter() - start) * 1000)

        cleaned = _clean_candidates(candidates, self.config.top_k)
        if cleaned:
            self._cache[normalized] = cleaned

        return CandidateSuggestion(
            prefix=normalized,
            candidates=cleaned,
            latency_ms=latency_ms,
            source=source if cleaned else "fallback",
        )


def _clean_candidates(candidates: list[str], top_k: int) -> list[str]:
    dedup: list[str] = []
    seen: set[str] = set()

    for item in candidates:
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(text)
        if len(dedup) >= top_k:
            break

    return dedup
