"""
app/services/ollama_client.py — Ollama HTTP client.

Extracted from app/services/feedback.py (_request_chat with ollama=True).
Provides low-level access to Ollama /api/generate and /api/chat.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.config import QWEN_BASE_URL, QWEN_MODEL


class OllamaError(RuntimeError):
    pass


def generate(
    prompt: str,
    model: str | None = None,
    stream: bool = False,
    timeout: int = 60,
) -> str:
    """Call Ollama /api/generate and return the response text."""
    model = model or QWEN_MODEL
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": stream,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{QWEN_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read(1_000_000))
        result = data.get("response", "")
        if not isinstance(result, str) or not result.strip():
            raise OllamaError("Ollama returned an empty response")
        return result.strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc


def is_available(timeout: float = 2.0) -> bool:
    """Check if Ollama is reachable."""
    try:
        req = urllib.request.Request(f"{QWEN_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False
