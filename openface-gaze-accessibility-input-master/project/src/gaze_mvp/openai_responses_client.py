from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List


class OpenAIClientError(RuntimeError):
    """Raised when OpenAI request fails or response is malformed."""


@dataclass
class OpenAIResponsesClient:
    base_url: str
    model: str
    api_key_env: str
    temperature: float = 0.2
    max_output_tokens: int = 64
    timeout_seconds: int = 30

    def _build_request_body(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
        }

    def _extract_text(self, response_obj: Dict[str, Any]) -> str:
        # Some compatible gateways may expose a shortcut field.
        output_text = response_obj.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = response_obj.get("output")
        if not isinstance(output, list):
            raise OpenAIClientError("Invalid response format: missing output.")

        texts: List[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            contents = item.get("content")
            if not isinstance(contents, list):
                continue
            for content in contents:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())

        if not texts:
            raise OpenAIClientError("No output text found in response.")
        return "\n".join(texts)

    def request_text(self, system_prompt: str, user_prompt: str) -> str:
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise OpenAIClientError(f"Environment variable {self.api_key_env} is not set.")

        body = self._build_request_body(system_prompt, user_prompt)
        req = urllib.request.Request(
            url=f"{self.base_url}/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenAIClientError(f"HTTP {exc.code} from OpenAI API: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OpenAIClientError(f"Network error when calling OpenAI API: {exc}") from exc

        try:
            obj = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError(f"Invalid JSON response: {payload[:500]}") from exc

        return self._extract_text(obj)
