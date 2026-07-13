"""OpenAI-compatible reasoning backend: one adapter for OpenAI, a local Ollama/vLLM server, and any
endpoint that speaks ``/v1/chat/completions``. Same ``ReasoningModel`` interface as the Claude
backend. The key is read from the environment at call time and never stored (PROJECT.md §6).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .adapter import (
    BaseReasoningModel,
    ReasoningError,
    ReasoningRequest,
    ReasoningResponse,
    ReasoningTimeout,
    Usage,
    _is_timeout,
)

# OpenAI finish_reason -> the interface's stop_reason vocabulary (what the memo + checks understand).
_FINISH_MAP = {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal", "tool_calls": "tool_use"}


class OpenAICompatibleReasoningModel(BaseReasoningModel):
    """Backend for any OpenAI-style chat-completions endpoint. ``api_key_env`` is the *name* of the env
    var holding the key (``None`` for keyless local servers). Inject ``client`` to unit-test the
    request/response mapping without the SDK or a live call.
    """

    # A reasoning-appropriate output ceiling. Unlike Claude — whose hidden "thinking" tokens count
    # against max_tokens, so it needs a large budget — OpenAI and local models emit only visible
    # tokens. A modest ceiling is sufficient for a rationale/synthesis and is the right way to call a
    # local model (a 16k num_predict is wasteful and can strain a small local context).
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key_env: Optional[str] = None,
        default_max_tokens: int = 2048,
        client: Any = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.default_max_tokens = default_max_tokens
        self._client = client

    @property
    def name(self) -> str:
        return self.model

    def _api_key(self) -> str:
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if not key:
                raise ReasoningError(f"{self.api_key_env} is not set in the environment")
            return key
        return "local"  # keyless servers ignore it, but the SDK requires a non-empty value

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:  # optional dependency
                raise ReasoningError("the 'openai' package is required (pip install openai)") from exc
            self._client = openai.OpenAI(base_url=self.base_url, api_key=self._api_key())
        return self._client

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        client = self._get_client()
        # Cap the request to a sensible visible-token budget (see default_max_tokens): a Claude-sized
        # 16k budget is wasteful here and, for a local server, kinder to keep modest.
        max_tokens = (
            min(request.max_tokens, self.default_max_tokens)
            if request.max_tokens is not None
            else self.default_max_tokens
        )
        messages = [{"role": "system", "content": request.system}] if request.system else []
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        params: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": request.temperature,
        }
        if request.stop_sequences:
            params["stop"] = request.stop_sequences
        try:
            resp = client.chat.completions.create(**params)
        except Exception as exc:  # normalize any SDK/transport failure to the interface's error
            if _is_timeout(exc):
                raise ReasoningTimeout(f"request timed out: {exc}") from exc
            raise ReasoningError(f"request failed: {exc}") from exc
        try:
            return self._to_response(resp)
        except ReasoningError:
            raise
        except Exception as exc:  # a malformed payload is a failure, not a raw error to callers
            raise ReasoningError(f"could not decode response: {exc}") from exc

    @staticmethod
    def _to_response(resp: Any) -> ReasoningResponse:
        choices = getattr(resp, "choices", None)
        if not choices:
            raise ReasoningError("malformed response: no choices")
        choice = choices[0]
        text = getattr(getattr(choice, "message", None), "content", None) or ""
        finish = getattr(choice, "finish_reason", None) or "stop"
        raw_usage = getattr(resp, "usage", None)
        usage = (
            Usage(
                input_tokens=getattr(raw_usage, "prompt_tokens", None),
                output_tokens=getattr(raw_usage, "completion_tokens", None),
            )
            if raw_usage is not None
            else None
        )
        return ReasoningResponse(text=text, stop_reason=_FINISH_MAP.get(finish, finish), usage=usage, raw=resp)
