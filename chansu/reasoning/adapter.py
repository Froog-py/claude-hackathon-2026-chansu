"""The model-adapter interface (PROJECT.md §10, layer 2).

This is the *contract* a reasoning backend must satisfy to drive Chansu. Claude is the
production backend (adapter added Day 3). A local model is a stretch backend that plugs in
here or not at all — it must never modify the core or the Claude path (see
docs/local-model-handoff.md).

The interface is deliberately provider-neutral: a request is a system prompt + a message
list + optional tool specs; a response is text + optional tool calls + a stop reason. This
maps cleanly onto Claude's Messages API, OpenAI-style chat, and local servers (llama.cpp,
Ollama, vLLM) that expose function calling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Protocol, runtime_checkable


@dataclass
class Message:
    role: str          # "user" | "assistant"
    content: str


@dataclass
class ToolSpec:
    """A callable the backend may invoke. ``input_schema`` is JSON Schema."""

    name: str
    description: str
    input_schema: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ReasoningRequest:
    system: str
    messages: list[Message]
    tools: list[ToolSpec] = field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.0
    stop_sequences: list[str] = field(default_factory=list)


@dataclass
class Usage:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class ReasoningResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"   # "end_turn" | "tool_use" | "max_tokens"
    usage: Optional[Usage] = None
    raw: Any = None                 # backend-native payload, for debugging only


class ReasoningError(Exception):
    """Any backend failure. Never return partial text as if it were a complete answer."""


class ReasoningTimeout(ReasoningError):
    """The backend did not respond within its deadline."""


@runtime_checkable
class ReasoningModel(Protocol):
    """The contract. A backend implements ``complete``; ``stream`` is optional-but-required
    by signature (wrap ``complete`` if the backend cannot stream)."""

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        """One synchronous request -> response. Raise ``ReasoningError`` on failure."""
        ...

    def stream(self, request: ReasoningRequest) -> Iterator[str]:
        """Yield text chunks as they arrive. **v1 streams text only** — tool calls,
        ``stop_reason``, and usage are not recoverable from the stream; call ``complete`` for a
        full response. (A typed-event stream — TextDelta/ToolCallDelta/Completed — is a Day-3
        upgrade tracked in SOMEDAY.md.) A non-streaming backend may yield once."""
        ...


class BaseReasoningModel:
    """Convenience base: implement ``complete``; get a default single-chunk ``stream``."""

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        raise NotImplementedError

    def stream(self, request: ReasoningRequest) -> Iterator[str]:
        yield self.complete(request).text


class EchoReasoningModel(BaseReasoningModel):
    """Trivial conformance stub (no real reasoning). Lets the interface be smoke-tested
    before any real backend exists. Not part of the production path."""

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        last = request.messages[-1].content if request.messages else ""
        return ReasoningResponse(
            text=f"[echo] {last}", stop_reason="end_turn", usage=Usage(0, 0)
        )


class ClaudeReasoningModel(BaseReasoningModel):
    """The production reasoning backend — Claude (Opus), behind the same interface any other
    backend implements (this is what the local-model handoff mirrors).

    Runtime notes baked in from the Anthropic API:
      * Default model ``claude-opus-4-8`` (PROJECT.md: "Claude (Opus)").
      * Adaptive thinking + high effort for multi-step scientific reasoning.
      * Opus 4.8 rejects sampling params (``temperature``/``top_p``/``budget_tokens``) with a
        400 — so ``ReasoningRequest.temperature`` is intentionally NOT forwarded.
      * Credentials resolve from the environment at call time (``ANTHROPIC_API_KEY`` or an
        ``ant`` profile). This class never reads or holds a key itself.
      * A ``stop_reason == "refusal"`` is a valid 200 outcome, surfaced honestly (empty text +
        ``stop_reason="refusal"``) rather than faked into a completed answer (PROJECT.md §6).

    ``anthropic`` is an optional dependency, imported lazily; inject ``client`` to unit-test the
    request/response mapping without the SDK or a live call.
    """

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        default_max_tokens: int = 4096,
        effort: str = "high",
        client: Any = None,
    ) -> None:
        self.model = model
        self.default_max_tokens = default_max_tokens
        self.effort = effort
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # optional dependency
                raise ReasoningError(
                    "the 'anthropic' package is required for ClaudeReasoningModel "
                    "(pip install anthropic)"
                ) from exc
            self._client = anthropic.Anthropic()  # resolves credentials from the environment
        return self._client

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        client = self._get_client()
        params: dict = {
            "model": self.model,
            "max_tokens": request.max_tokens or self.default_max_tokens,
            "system": request.system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
        }
        if request.tools:
            params["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in request.tools
            ]
        if request.stop_sequences:
            params["stop_sequences"] = request.stop_sequences
        # NOTE: request.temperature is deliberately not forwarded — Opus 4.8 rejects it (400).

        try:
            resp = client.messages.create(**params)
        except Exception as exc:  # normalize any SDK/transport failure to the interface's error
            raise ReasoningError(f"Claude request failed: {exc}") from exc

        return self._to_response(resp)

    @staticmethod
    def _to_response(resp: Any) -> ReasoningResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(resp, "content", []) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))

        usage = None
        raw_usage = getattr(resp, "usage", None)
        if raw_usage is not None:
            usage = Usage(
                input_tokens=getattr(raw_usage, "input_tokens", None),
                output_tokens=getattr(raw_usage, "output_tokens", None),
            )
        stop_reason = getattr(resp, "stop_reason", None) or "end_turn"
        # Refusal is honest failure — return it tagged, never dress an empty/partial reply up
        # as a complete answer. Callers must check stop_reason before trusting the text.
        return ReasoningResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw=resp,
        )
