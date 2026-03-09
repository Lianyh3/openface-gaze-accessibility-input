from __future__ import annotations

from pathlib import Path

from gaze_mvp.candidate_reranker import CandidateReranker
from gaze_mvp.config_loader import AppConfig, load_app_config
from gaze_mvp.openai_responses_client import OpenAIResponsesClient


def build_reranker_from_config(config_path: Path) -> tuple[AppConfig, CandidateReranker]:
    config = load_app_config(config_path)

    client = None
    if config.llm.provider == "openai" and config.llm.api_style == "responses":
        client = OpenAIResponsesClient(
            base_url=config.llm.base_url,
            model=config.llm.model,
            api_key_env=config.llm.api_key_env,
            temperature=config.llm.temperature,
            max_output_tokens=config.llm.max_output_tokens,
            timeout_seconds=config.llm.timeout_seconds,
        )

    return config, CandidateReranker(client=client)
