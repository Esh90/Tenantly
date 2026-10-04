"""Free backup model (Groq, OpenAI-compatible tool calling) for when the paid budget is used up
or the paid API is unavailable. Nothing it returns is trusted more than the primary model's:
quotes still have to match the source byte for byte, and dates are still computed by code."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("tenantly.groq")

URL = "https://api.groq.com/openai/v1/chat/completions"


def available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def model_name() -> str:
    return "groq:" + os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")


def call_tool(system: str, user: str, tool: dict, max_tokens: int = 4000) -> dict | None:
    """One forced function call. Returns the tool arguments, or None on any failure."""
    body = {
        "model": model_name().split(":", 1)[1],
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "tools": [{"type": "function", "function": {
            "name": tool["name"], "description": tool["description"], "parameters": tool["input_schema"]}}],
        "tool_choice": {"type": "function", "function": {"name": tool["name"]}},
    }  # fmt: skip
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}", "Content-Type": "application/json",
                 "User-Agent": "tenantly/0.1"},
    )  # fmt: skip
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        calls = data["choices"][0]["message"].get("tool_calls") or []
        return json.loads(calls[0]["function"]["arguments"]) if calls else None
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError) as exc:
        log.warning("groq fallback failed: %s", type(exc).__name__)
        return None
