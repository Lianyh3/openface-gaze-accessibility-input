from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from gaze_keyboard.common.config import AiConfig


@dataclass(slots=True)
class CodexClient:
    config: AiConfig

    def complete(self, prompt: str) -> tuple[list[str], int, str]:
        api_key = os.getenv(self.config.api_key_env, "").strip()
        if not api_key:
            return [], 0, "fallback"

        payload = {
            "model": self.config.model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        }

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.config.endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_ms / 1000.0) as response:
                response_body = response.read().decode("utf-8")
                candidates = _extract_candidates(response_body)
                return candidates[: self.config.top_k], 0, "llm"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return [], 0, "fallback"


def _extract_candidates(response_body: str) -> list[str]:
    payload = json.loads(response_body)

    output_items = payload.get("output", [])
    text_fragments: list[str] = []
    for item in output_items:
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    text_fragments.append(text)

    joined = "\n".join(text_fragments).strip()
    if not joined:
        return []

    try:
        parsed = json.loads(joined)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass

    lines = [line.strip(" -•\t") for line in joined.splitlines()]
    return [line for line in lines if line]
