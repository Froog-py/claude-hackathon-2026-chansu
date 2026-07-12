"""Local OpenAI-compatible reasoning backend (stretch goal).

Maps :class:`~chansu.reasoning.adapter.ReasoningRequest` to a local
``/v1/chat/completions`` endpoint (Ollama, llama.cpp, vLLM, LM Studio).
Not part of the production Claude path.

Security posture for this deployment: by default the client only talks to
loopback hosts and refuses HTTP redirects (so a local peer cannot bounce
prompt payloads off-machine). ``http``/``https`` is always required.
Set ``CHANSU_LOCAL_ALLOW_REMOTE=1`` to opt out of the loopback host allowlist
for intentional non-local HTTP endpoints.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from chansu.reasoning.adapter import (
    BaseReasoningModel,
    ReasoningError,
    ReasoningRequest,
    ReasoningResponse,
    ReasoningTimeout,
    ToolCall,
    Usage,
)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024  # 16 MiB cap against a hostile local peer


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_base_url(url: str, *, require_loopback: bool) -> None:
    """Reject non-HTTP(S) schemes always; optionally require a loopback host."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ReasoningError(f"Local model base_url must be http(s); got {parsed.scheme!r}")
    if not require_loopback:
        return
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        raise ReasoningError(
            f"Local model base_url host must be loopback ({', '.join(sorted(_LOOPBACK_HOSTS))}); "
            f"got {host!r}. Set CHANSU_LOCAL_ALLOW_REMOTE=1 to override."
        )


def _map_finish_reason(finish_reason: str | None) -> str:
    mapping = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
    }
    return mapping.get(finish_reason or "stop", "end_turn")


def _is_timeout_reason(reason: Any) -> bool:
    if isinstance(reason, TimeoutError):
        return True
    # Older urllib/socket paths may surface a bare timeout type or message.
    if reason is socket.timeout or type(reason) is socket.timeout:  # noqa: E721
        return True
    text = str(reason).lower()
    return "timed out" in text or "timeout" in text


def _parse_tool_arguments(raw: str | dict | None) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReasoningError(f"Invalid tool-call arguments JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ReasoningError("Tool-call arguments must decode to a JSON object")
    return parsed


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so prompt payloads cannot leave the intended host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, N802
        raise ReasoningError(
            f"Local model refused HTTP redirect ({code}) to {newurl!r} "
            "(redirects disabled to keep reasoning payloads on the configured host)"
        )


class LocalReasoningModel(BaseReasoningModel):
    """Reasoning backend backed by a local OpenAI-compatible chat server."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout_s: float = 120.0,
        allow_remote: bool | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("CHANSU_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("CHANSU_LOCAL_MODEL", "")
        if not self.model:
            raise ReasoningError(
                "Local model name is required (constructor or CHANSU_LOCAL_MODEL)"
            )
        self.timeout_s = timeout_s
        if allow_remote is None:
            allow_remote = _env_truthy("CHANSU_LOCAL_ALLOW_REMOTE")
        self.allow_remote = allow_remote
        _validate_base_url(self.base_url, require_loopback=not self.allow_remote)
        self._opener = urllib.request.build_opener(_NoRedirectHandler)

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        payload = self._build_payload(request)
        raw = self._post_json(f"{self.base_url}/chat/completions", payload)
        return self._parse_response(raw)

    def _build_payload(self, request: ReasoningRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for message in request.messages:
            messages.append({"role": message.role, "content": message.content})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = "auto"
        return payload

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        _validate_base_url(url, require_loopback=not self.allow_remote)

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                data = resp.read(_MAX_RESPONSE_BYTES + 1)
        except ReasoningError:
            raise
        except TimeoutError as exc:
            raise ReasoningTimeout(f"Local model timed out after {self.timeout_s}s") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
            raise ReasoningError(f"Local model HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if _is_timeout_reason(exc.reason):
                raise ReasoningTimeout(
                    f"Local model timed out after {self.timeout_s}s"
                ) from exc
            raise ReasoningError(f"Local model connection failed: {exc.reason}") from exc

        if len(data) > _MAX_RESPONSE_BYTES:
            raise ReasoningError(
                f"Local model response exceeded {_MAX_RESPONSE_BYTES} bytes"
            )

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ReasoningError(f"Local model returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ReasoningError("Local model response must be a JSON object")
        return parsed

    def _parse_response(self, raw: dict[str, Any]) -> ReasoningResponse:
        choices = raw.get("choices")
        if not choices or not isinstance(choices, list):
            raise ReasoningError("Local model response missing choices")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise ReasoningError("Local model choice must be an object")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise ReasoningError("Local model response missing message")

        text = message.get("content") or ""
        if not isinstance(text, str):
            raise ReasoningError("Local model message content must be a string")

        tool_calls: list[ToolCall] = []
        for idx, call in enumerate(message.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            fn = call.get("function") or {}
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if not isinstance(name, str) or not name:
                continue
            tool_calls.append(
                ToolCall(
                    id=str(call.get("id") or f"call_{idx}"),
                    name=name,
                    arguments=_parse_tool_arguments(fn.get("arguments")),
                )
            )

        usage_raw = raw.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            usage = Usage(
                input_tokens=usage_raw.get("prompt_tokens"),
                output_tokens=usage_raw.get("completion_tokens"),
            )

        stop_reason = _map_finish_reason(choice.get("finish_reason"))
        if tool_calls and stop_reason == "end_turn":
            stop_reason = "tool_use"
        elif stop_reason == "tool_use" and not tool_calls:
            # finish_reason said tools, but none survived parsing — honest end_turn.
            stop_reason = "end_turn"

        return ReasoningResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw=raw,
        )
