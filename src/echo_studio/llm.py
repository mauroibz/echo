"""A client for language-model servers: one completion, and the model list (stdlib only).

The chat completions endpoint is what OpenAI, the providers that copy its API and the local
servers (llama.cpp, Ollama, vLLM) have in common, and one POST needs no SDK. Anthropic's API is
spoken natively (Messages), chosen by the server's address: its OpenAI-compatible layer is meant
for trying models out, and Echo would rather not lean on it.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import config

TIMEOUT_S = 300  # a long meeting's summary from a local server on a modest GPU takes minutes
MAX_TOKENS = 2048  # room for a summary of ~4,000 characters; length is asked for in the prompt
TEMPERATURE = 0.3

ANTHROPIC_HOSTS = {"api.anthropic.com"}
ANTHROPIC_VERSION = "2023-06-01"
# Anthropic's current models always think before answering, and thinking counts against max_tokens:
# room for both, well under the time a non-streamed request may take.
ANTHROPIC_MAX_TOKENS = 16000
# A declined request is answered by another model in the same call ("fallbacks"). Models that do
# not offer it reject the field, and the request is sent again without it.
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Some local servers return a reasoning model's thinking inline, before the answer.
_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


class LLMError(Exception):
    """The server could not be reached or refused the request; the message says why."""


def is_anthropic(url: str) -> bool:
    return config.host(url) in ANTHROPIC_HOSTS


def _request(url: str, payload: dict | None, timeout: float, key: str | None = None,
             extra: dict | None = None) -> dict:
    headers = {"Accept": "application/json", **(extra or {})}
    key = config.api_key(url) if key is None else key
    if key and is_anthropic(url):
        headers["x-api-key"] = key
        headers["anthropic-version"] = ANTHROPIC_VERSION
    elif key:
        headers["Authorization"] = f"Bearer {key}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise LLMError(f"the server answered {e.code}: {_error_text(e)}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise LLMError(f"could not reach {config.host(url) or url}: {reason}") from None
    try:
        return json.loads(body)
    except ValueError:
        raise LLMError("the server's answer is not JSON (is the address the API's, ending in /v1?)") from None


def _error_text(e: urllib.error.HTTPError) -> str:
    try:
        raw = e.read().decode("utf-8", "replace")
    except OSError:
        return e.reason or ""
    try:
        err = json.loads(raw).get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
    except (ValueError, AttributeError):
        pass
    return raw.strip()[:300] or str(e.reason or "")


def _base(cfg: config.Config) -> str:
    return cfg.llm_url.strip().rstrip("/")


def complete(system: str, user: str, cfg: config.Config | None = None) -> str:
    cfg = cfg or config.load()
    if not cfg.enabled:
        raise LLMError("no server is set up (Settings, Summaries)")
    if is_anthropic(cfg.llm_url):
        return _complete_anthropic(system, user, cfg)
    payload = {"model": cfg.llm_model, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    url = _base(cfg) + "/chat/completions"
    try:
        reply = _request(url, payload, TIMEOUT_S)
    except LLMError as e:
        # Some providers' newer models take max_completion_tokens and reject max_tokens outright.
        if "max_tokens" not in str(e):
            raise
        del payload["max_tokens"]
        reply = _request(url, payload, TIMEOUT_S)
    try:
        text = reply["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError("the server's answer has no message") from None
    return _THINK.sub("", text).strip()


def _complete_anthropic(system: str, user: str, cfg: config.Config) -> str:
    # No temperature: Anthropic's current models refuse sampling settings.
    payload = {"model": cfg.llm_model, "max_tokens": ANTHROPIC_MAX_TOKENS, "system": system,
               "messages": [{"role": "user", "content": user}]}
    url = _base(cfg) + "/messages"
    try:
        reply = _request(url, {**payload, "fallbacks": "default"}, TIMEOUT_S,
                         extra={"anthropic-beta": ANTHROPIC_FALLBACK_BETA})
    except LLMError as e:
        if "fallback" not in str(e).lower():
            raise
        reply = _request(url, payload, TIMEOUT_S)
    stop = reply.get("stop_reason")
    if stop == "refusal":
        raise LLMError("the model declined to summarize this recording")
    blocks = reply.get("content")
    if not isinstance(blocks, list):
        raise LLMError("the server's answer has no message")
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    if stop == "max_tokens":
        raise LLMError("the answer was cut off before it ended")
    return text.strip()


def models(cfg: config.Config | None = None, timeout: float = 10, key: str | None = None) -> list[str]:
    """The server's model names; `key` tries a key before it is saved."""
    cfg = cfg or config.load()
    query = "?limit=1000" if is_anthropic(cfg.llm_url) else ""  # Anthropic lists 20 by default
    reply = _request(_base(cfg) + "/models" + query, None, timeout, key)
    return [m.get("id", "") for m in reply.get("data", []) if isinstance(m, dict)]
