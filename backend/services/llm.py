"""OpenRouter client (OpenAI-compatible chat completions in JSON mode).

The key is read from the process environment only and is never logged. Every caller catches
LLMUnavailable and uses its deterministic fallback, so the app works without a key.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger("corvo.llm")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
TIMEOUT_SECONDS = 30
RETRY_BACKOFF_SECONDS = 1
RETRY_STATUSES = {429, 500, 502, 503, 504}
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class LLMUnavailable(RuntimeError):
    """The LLM could not be used; the caller falls back to rule-based logic."""


def model() -> str:
    return os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL


def base_url() -> str:
    return (os.environ.get("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def status() -> tuple[bool, str]:
    """(enabled, reason). Never reveals the key."""
    if os.environ.get("LLM_DISABLED", "").strip() in ("1", "true", "yes"):
        return False, "LLM_DISABLED"
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return False, "no OPENROUTER_API_KEY"
    return True, ""


def _parse(content: str) -> dict:
    text = content or ""
    fence = _FENCE.match(text)
    if fence:
        text = fence.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise LLMUnavailable("reply was not JSON")
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMUnavailable("reply was not JSON") from exc
    if not isinstance(value, dict):
        raise LLMUnavailable("reply was not a JSON object")
    return value


def complete_json(system: str, user: str, schema_hint: str = "", *, max_tokens: int = 2000) -> dict:
    enabled, reason = status()
    if not enabled:
        raise LLMUnavailable(reason)
    key = os.environ["OPENROUTER_API_KEY"].strip()
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": os.environ.get("APP_URL", "http://localhost:5173"),
        "X-Title": "Cantill PR-to-PO",
    }
    sys_text = system + (f"\n\nReply with one JSON object only. Shape:\n{schema_hint}" if schema_hint else "")
    body = {
        "model": model(),
        "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    url = f"{base_url()}/chat/completions"
    last_reason = "unknown error"
    for attempt in range(2):
        started = time.monotonic()
        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last_reason = type(exc).__name__
            log.warning("LLM call failed model=%s reason=%s latency=%.1fs", model(), last_reason,
                        time.monotonic() - started)
            if attempt == 0:
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise LLMUnavailable(last_reason) from None
        latency = time.monotonic() - started
        if resp.status_code != 200:
            last_reason = f"HTTP {resp.status_code}"
            log.warning("LLM call failed status=%s model=%s latency=%.1fs", resp.status_code, model(), latency)
            if attempt == 0 and resp.status_code in RETRY_STATUSES:
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise LLMUnavailable(last_reason)
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            log.warning("LLM reply had no content model=%s latency=%.1fs", model(), latency)
            raise LLMUnavailable("reply had no content") from None
        log.info("LLM call ok model=%s latency=%.1fs", model(), latency)
        return _parse(content)
    raise LLMUnavailable(last_reason)
