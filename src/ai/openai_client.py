from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class OpenAiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def chat_json(self, model: str, system: str, user: str) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
        }
        response = self._post_json("https://api.openai.com/v1/chat/completions", payload)
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)

    def speech_mp3(self, model: str, voice: str, text: str) -> bytes:
        payload = {
            "model": model,
            "voice": voice,
            "input": text,
            "format": "mp3",
        }
        request = Request(
            "https://api.openai.com/v1/audio/speech",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                return response.read()
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI speech request failed: {error.code} {body}") from error

    def _post_json(self, url: str, payload: dict) -> dict:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI request failed: {error.code} {body}") from error

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
