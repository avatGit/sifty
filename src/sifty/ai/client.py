"""Thin wrapper around a local Ollama server.

Everything degrades gracefully: if Ollama isn't running, :func:`is_available`
returns ``False`` and callers fall back to non-AI behaviour instead of crashing.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import load_config


class OllamaUnavailable(Exception):
    """Raised when the local Ollama server can't be reached."""


@dataclass
class OllamaClient:
    host: str
    model: str
    timeout: float

    @classmethod
    def from_config(cls, config=None) -> "OllamaClient":
        config = config or load_config()
        ai = config.section("ai")
        return cls(
            host=ai.get("host", "http://localhost:11434"),
            model=ai.get("model", "qwen2.5:3b"),
            timeout=float(ai.get("timeout_seconds", 60)),
        )

    def is_available(self) -> bool:
        """Return True if the Ollama server responds to a tags request."""
        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def chat(self, system: str, user: str) -> str:
        """Send a single-turn chat and return the assistant's text."""
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailable(str(exc)) from exc
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()
