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
        """Yield text chunks as they arrive. Tool calls surface on a final aggregated
        ``complete``-style response; a non-streaming backend may yield once."""
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
