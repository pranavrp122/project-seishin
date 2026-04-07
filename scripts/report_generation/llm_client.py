"""Non-streaming vLLM OpenAI-style completions for structured report steps."""
import json
from typing import Optional

import requests

from .config import BRAIN_URL, MODEL_NAME


def complete(
    prompt: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.2,
    stop: Optional[list[str]] = None,
    timeout: int = 90,
) -> str:
    payload: dict = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if stop:
        payload["stop"] = stop
    r = requests.post(BRAIN_URL, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Brain HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    choice = data.get("choices", [{}])[0]
    return (choice.get("text") or "").strip()


def safe_complete(*args, **kwargs) -> str:
    try:
        return complete(*args, **kwargs)
    except (requests.RequestException, json.JSONDecodeError, KeyError, RuntimeError):
        return ""
