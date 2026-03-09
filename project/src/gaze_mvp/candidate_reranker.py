from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from gaze_mvp.openai_responses_client import OpenAIClientError, OpenAIResponsesClient


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        v = item.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result


def _extract_json_array(text: str) -> List[str]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("No JSON array found in model output.")
    parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("Model output is not a JSON array.")
    return [str(v).strip() for v in parsed if str(v).strip()]


def _heuristic_score(candidate: str, prefix_text: str) -> float:
    # Prefer candidates matching recent context and shorter candidates for quicker dwell selection.
    context_tail = prefix_text[-8:].strip()
    score = 0.0
    if context_tail and candidate.startswith(context_tail[-1:]):
        score += 2.0
    if context_tail and candidate in context_tail:
        score += 1.5
    overlap = len(set(candidate) & set(context_tail)) if context_tail else 0
    score += overlap * 0.2
    score += max(0.0, 1.2 - (len(candidate) * 0.08))
    return score


def heuristic_rerank(candidates: Sequence[str], prefix_text: str) -> List[str]:
    cleaned = _dedupe_keep_order(candidates)
    return sorted(cleaned, key=lambda c: _heuristic_score(c, prefix_text), reverse=True)


def _merge_ranked_with_original(model_ranked: Sequence[str], original: Sequence[str]) -> List[str]:
    original_clean = _dedupe_keep_order(original)
    allowed = set(original_clean)

    merged: List[str] = []
    used = set()
    for item in model_ranked:
        if item in allowed and item not in used:
            merged.append(item)
            used.add(item)
    for item in original_clean:
        if item not in used:
            merged.append(item)
            used.add(item)
    return merged


@dataclass
class RerankResult:
    ranked: List[str]
    source: str
    debug_message: str = ""


class CandidateReranker:
    def __init__(self, client: OpenAIResponsesClient | None):
        self.client = client

    def rerank(self, prefix_text: str, candidates: Sequence[str]) -> RerankResult:
        cleaned = _dedupe_keep_order(candidates)
        if not cleaned:
            return RerankResult(ranked=[], source="empty")

        if self.client is None:
            return RerankResult(
                ranked=heuristic_rerank(cleaned, prefix_text),
                source="heuristic",
                debug_message="No OpenAI client configured.",
            )

        system_prompt = (
            "你是中文输入法候选词重排器。"
            "你的任务是根据已有输入上下文，对候选词做从高到低排序。"
            "仅输出 JSON 数组，不要输出解释。"
        )
        user_prompt = json.dumps(
            {
                "task": "rerank_candidates",
                "prefix_text": prefix_text,
                "candidates": cleaned,
                "requirements": [
                    "优先保证语义连贯",
                    "优先高频自然表达",
                    "尽量将最可能候选放在前3位",
                ],
                "output_format": ["候选1", "候选2", "候选3"],
            },
            ensure_ascii=False,
        )

        try:
            output_text = self.client.request_text(system_prompt=system_prompt, user_prompt=user_prompt)
            llm_ranked = _extract_json_array(output_text)
            merged = _merge_ranked_with_original(llm_ranked, cleaned)
            return RerankResult(ranked=merged, source="openai")
        except (OpenAIClientError, ValueError, json.JSONDecodeError) as exc:
            return RerankResult(
                ranked=heuristic_rerank(cleaned, prefix_text),
                source="heuristic_fallback",
                debug_message=str(exc),
            )
