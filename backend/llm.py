"""
One place for model access.

- moonshot_client(): the Kimi client. Every call is logged to
  llm_usage.jsonl (step, tokens, web searches, seconds) so the
  Moonshot bill can be traced to the step that caused it.
- local_chat_json(): the same kind of JSON call on a local Ollama
  model. A step runs locally when .env says so, e.g.
  QUALIFY_BACKEND=local (default: kimi).
"""

from __future__ import annotations

import inspect
import json
import os
import threading
import time

from datetime import datetime, timezone
from pathlib import Path

import requests

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")

USAGE_LOG = ROOT / "llm_usage.jsonl"

OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://127.0.0.1:11434",
).rstrip("/")

LOCAL_MODEL = os.environ.get(
    "LOCAL_MODEL",
    "qwen3.8:27b-q4_K_M",
)

_log_lock = threading.Lock()

# Wrapper functions that sit between a step and the API; the
# step name is the first caller that is not one of these.
_WRAPPERS = {
    "moonshot_chat_create",
    "logged_create",
    "local_chat_json",
    "log_usage",
    "caller_step",
}


def backend_for(step: str) -> str:
    """'kimi' or 'local' for a step, from <STEP>_BACKEND in .env."""

    return (
        os.environ.get(f"{step.upper()}_BACKEND", "kimi")
        .strip()
        .lower()
    )


def caller_step() -> str:

    for frame in inspect.stack()[1:]:
        path = Path(frame.filename)

        if (
            path.parent == ROOT
            and path.stem != "llm"
            and frame.function not in _WRAPPERS
        ):
            return f"{path.stem}.{frame.function}"

    return "unknown"


def log_usage(entry: dict) -> None:
    """Append one line per model call. Never breaks a run."""

    try:
        line = json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                **entry,
            },
            ensure_ascii=False,
        )

        with _log_lock:
            with USAGE_LOG.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    except Exception:
        pass


def moonshot_client() -> OpenAI:

    client = OpenAI(
        api_key=os.environ["MOONSHOT_API_KEY"],
        base_url="https://api.moonshot.ai/v1",
    )

    original = client.chat.completions.create

    def logged_create(*args, **kwargs):

        started = time.time()
        response = original(*args, **kwargs)

        try:
            usage = getattr(response, "usage", None)
            choice = response.choices[0]
            tool_calls = choice.message.tool_calls or []

            log_usage(
                {
                    "backend": "kimi",
                    "step": caller_step(),
                    "model": kwargs.get("model", ""),
                    # Includes web-search result text fed back
                    # to the model, which is billed as input.
                    "prompt_tokens": getattr(
                        usage, "prompt_tokens", None
                    ),
                    "completion_tokens": getattr(
                        usage, "completion_tokens", None
                    ),
                    "cached_tokens": getattr(
                        usage, "cached_tokens", None
                    ),
                    "web_searches": sum(
                        1
                        for call in tool_calls
                        if call.function.name == "$web_search"
                    ),
                    "seconds": round(time.time() - started, 1),
                }
            )

        except Exception:
            pass

        return response

    client.chat.completions.create = logged_create

    return client


def local_chat_json(
    messages: list[dict],
    max_tokens: int | None = None,
) -> str:
    """
    Ask the local model for a JSON answer; returns the raw
    content. Raises a clear error when Ollama is not running
    instead of letting the step silently produce nothing.
    """

    options = {
        "num_ctx": 16384,
        "temperature": 0.2,
    }

    if max_tokens:
        options["num_predict"] = max_tokens

    started = time.time()

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": LOCAL_MODEL,
                "messages": messages,
                "stream": False,
                "format": "json",
                "think": False,
                "options": options,
            },
            # The 27B model needs ~3 min per batch of 10.
            timeout=1800,
        )

    except requests.ConnectionError as exc:
        raise RuntimeError(
            f"Local model not reachable at {OLLAMA_URL}. "
            "Start Ollama (sudo systemctl start ollama) or set "
            "the step back to Kimi in .env."
        ) from exc

    response.raise_for_status()
    body = response.json()

    log_usage(
        {
            "backend": "local",
            "step": caller_step(),
            "model": LOCAL_MODEL,
            "prompt_tokens": body.get("prompt_eval_count"),
            "completion_tokens": body.get("eval_count"),
            "web_searches": 0,
            "seconds": round(time.time() - started, 1),
        }
    )

    return body["message"]["content"]
