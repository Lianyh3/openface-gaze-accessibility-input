from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Sequence

from gaze_mvp.candidate_reranker import CandidateReranker, RerankResult


@dataclass
class KeyboardState:
    committed_text: str
    composing_buffer: str
    ranked_candidates: List[str]
    rerank_source: str
    rerank_debug_message: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class KeyboardMVP:
    """
    A lightweight keyboard flow that can be driven by gaze dwell events later.
    For now it is command-driven (CLI), but keeps interfaces ready for UI hookup.
    """

    def __init__(self, reranker: CandidateReranker):
        self.reranker = reranker
        self.committed_text = ""
        self.composing_buffer = ""
        self._base_candidates: List[str] = []
        self._last_result = RerankResult(ranked=[], source="init", debug_message="")

    def type_text(self, text: str) -> KeyboardState:
        self.composing_buffer += text
        return self.get_state()

    def backspace(self) -> KeyboardState:
        if self.composing_buffer:
            self.composing_buffer = self.composing_buffer[:-1]
        elif self.committed_text:
            self.committed_text = self.committed_text[:-1]
        return self.get_state()

    def set_base_candidates(self, candidates: Sequence[str]) -> KeyboardState:
        self._base_candidates = [c.strip() for c in candidates if c.strip()]
        self._last_result = self.reranker.rerank(
            prefix_text=f"{self.committed_text}{self.composing_buffer}",
            candidates=self._base_candidates,
        )
        return self.get_state()

    def pick_candidate(self, index_1_based: int) -> KeyboardState:
        if index_1_based <= 0:
            raise ValueError("Candidate index must be positive.")
        ranked = self._last_result.ranked
        if index_1_based > len(ranked):
            raise IndexError(f"Candidate index out of range: {index_1_based} > {len(ranked)}")
        picked = ranked[index_1_based - 1]
        self.committed_text += picked
        self.composing_buffer = ""
        self._base_candidates = []
        self._last_result = RerankResult(ranked=[], source="picked", debug_message="")
        return self.get_state()

    def commit_buffer_directly(self) -> KeyboardState:
        self.committed_text += self.composing_buffer
        self.composing_buffer = ""
        self._base_candidates = []
        self._last_result = RerankResult(ranked=[], source="commit_direct", debug_message="")
        return self.get_state()

    def clear(self) -> KeyboardState:
        self.committed_text = ""
        self.composing_buffer = ""
        self._base_candidates = []
        self._last_result = RerankResult(ranked=[], source="cleared", debug_message="")
        return self.get_state()

    def get_state(self) -> KeyboardState:
        return KeyboardState(
            committed_text=self.committed_text,
            composing_buffer=self.composing_buffer,
            ranked_candidates=list(self._last_result.ranked),
            rerank_source=self._last_result.source,
            rerank_debug_message=self._last_result.debug_message,
        )
