from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, Sequence


class CandidateProvider(Protocol):
    def suggest(self, committed_text: str, composing_buffer: str, limit: int = 8) -> List[str]:
        """
        Return candidate strings for current composing buffer.
        """


@dataclass
class LexiconCandidateProvider:
    """
    A lightweight candidate provider for MVP stage.
    It can be replaced by IME/system dictionary later without changing event flow.
    """

    lexicon: Sequence[str]
    default_candidates: Sequence[str]

    def suggest(self, committed_text: str, composing_buffer: str, limit: int = 8) -> List[str]:
        query = composing_buffer.strip()
        committed_tail = committed_text[-1:] if committed_text else ""

        if not query:
            return list(self.default_candidates[:limit])

        startswith = [item for item in self.lexicon if item.startswith(query)]
        contains = [item for item in self.lexicon if query in item and item not in startswith]
        tail_match = [
            item
            for item in self.lexicon
            if committed_tail and item.startswith(committed_tail) and item not in startswith and item not in contains
        ]

        ordered = startswith + contains + tail_match + list(self.default_candidates)
        deduped: List[str] = []
        seen = set()
        for item in ordered:
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped


def build_default_provider() -> LexiconCandidateProvider:
    lexicon = [
        "你好",
        "您好",
        "谢谢",
        "请问",
        "可以",
        "不可以",
        "实验室",
        "图书馆",
        "食堂",
        "操场",
        "回宿舍",
        "去上课",
        "去开会",
        "今天",
        "明天",
        "现在",
        "马上",
        "我想",
        "我今天想去",
        "我现在需要",
        "请帮我",
        "打开文档",
        "发送消息",
        "完成作业",
        "开始实验",
        "结束实验",
    ]
    defaults = ["我想", "请帮我", "现在", "今天", "图书馆", "实验室", "食堂", "操场"]
    return LexiconCandidateProvider(lexicon=lexicon, default_candidates=defaults)
