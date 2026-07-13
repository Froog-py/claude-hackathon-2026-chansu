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
    """A conversation turn. **v1 carries text only.** The adapter can surface a returned
    ``tool_use`` request (see ``ReasoningResponse.tool_calls``), but feeding a tool *result* back
    as a follow-up turn needs typed assistant-tool-use / user-tool-result content with call-id
    correlation, which this provider-neutral contract does not yet model — tool support is
    receive-only for now (the full tool loop is a SOMEDAY item, not on the Day-4 path)."""

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
    max_tokens: Optional[int] = None   # None -> the backend's configured default
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
    # A successful (200) stop reason. Anthropic's current set includes end_turn, tool_use,
    # max_tokens, stop_sequence, pause_turn, refusal, model_context_window_exceeded. Callers MUST
    # check this before trusting ``text`` — refusal/max_tokens/pause mean the text is partial or
    # empty, not a complete answer. Backend-specific detail (matched stop sequence, refusal cause)
    # is available on ``raw``.
    stop_reason: str = "end_turn"
    # When ``stop_reason == "refusal"`` the backend also reports *why* it declined
    # (Anthropic: ``stop_details.category`` — e.g. ``"bio"`` for a life-sciences safety
    # false-positive). Surfaced first-class so the trust boundary can say not just *that* a
    # call was declined but *what* the model's own safety layer flagged (PROJECT.md §6).
    stop_category: Optional[str] = None
    usage: Optional[Usage] = None
    raw: Any = None                 # backend-native payload, for debugging only


class ReasoningError(Exception):
    """Any backend failure. Never return partial text as if it were a complete answer."""


class ReasoningTimeout(ReasoningError):
    """The backend did not respond within its deadline."""


def _is_timeout(exc: BaseException) -> bool:
    """True if an exception is a request timeout. Matched by type name up the MRO so the optional
    ``anthropic`` SDK need not be importable to classify its ``APITimeoutError`` alongside the
    stdlib ``TimeoutError`` (Codex P1: timeouts must map to ``ReasoningTimeout``)."""
    if isinstance(exc, TimeoutError):
        return True
    return any(t.__name__ in {"APITimeoutError", "Timeout"} for t in type(exc).__mro__)


@runtime_checkable
class ReasoningModel(Protocol):
    """The contract. A backend implements ``complete`` and exposes ``name``; ``stream`` is
    optional-but-required by signature (wrap ``complete`` if the backend cannot stream)."""

    @property
    def name(self) -> str:
        """A short identifier for the backing model (e.g. its model id). This is what the reasoning
        provenance tag names — ``[reasoning — <name>]`` — so the tag reflects whatever model is
        actually behind the interface, with no hardcoded vendor."""
        ...

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

    name: str = "reasoning-model"   # concrete backends override with their real model id

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        raise NotImplementedError

    def stream(self, request: ReasoningRequest) -> Iterator[str]:
        yield self.complete(request).text


class EchoReasoningModel(BaseReasoningModel):
    """Trivial conformance stub (no real reasoning). Lets the interface be smoke-tested
    before any real backend exists. Not part of the production path."""

    name = "echo"

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
      * Tool calls are **receive-only** in v1: a returned ``tool_use`` is surfaced as a
        ``ToolCall``, but feeding a tool *result* back into a follow-up turn is not yet modeled
        (see ``Message``) — the full tool loop is a SOMEDAY item, off the Day-4 path.
      * A malformed response (missing ``stop_reason``/``content``, or an undecodable block) raises
        ``ReasoningError``; a request timeout raises ``ReasoningTimeout`` — a failure is never
        promoted to an empty "success" (PROJECT.md §6).

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

    @property
    def name(self) -> str:
        """The configured model id — what the reasoning provenance tag names."""
        return self.model

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
        max_tokens = request.max_tokens if request.max_tokens is not None else self.default_max_tokens
        params: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
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
            if _is_timeout(exc):
                raise ReasoningTimeout(f"Claude request timed out: {exc}") from exc
            raise ReasoningError(f"Claude request failed: {exc}") from exc

        try:
            return self._to_response(resp)
        except ReasoningError:
            raise
        except Exception as exc:  # a malformed payload is a failure, not a raw TypeError to callers
            raise ReasoningError(f"could not decode Claude response: {exc}") from exc

    @staticmethod
    def _to_response(resp: Any) -> ReasoningResponse:
        # A well-formed Messages response always carries a stop_reason and a content list. Missing
        # either means the payload is malformed — fail honestly rather than promote it to an empty
        # "end_turn" success (Codex P1).
        stop_reason = getattr(resp, "stop_reason", None)
        if stop_reason is None:
            raise ReasoningError("malformed Claude response: missing stop_reason")
        content = getattr(resp, "content", None)
        if content is None:
            raise ReasoningError("malformed Claude response: missing content")

        # Refusal category (``stop_details.category``) when the backend supplies it — optional, and
        # absent on non-refusal stops and on the unit-test mocks, so read it defensively.
        stop_details = getattr(resp, "stop_details", None)
        stop_category = getattr(stop_details, "category", None) if stop_details is not None else None

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in content:
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
        # Refusal is honest failure — return it tagged, never dress an empty/partial reply up
        # as a complete answer. Callers must check stop_reason before trusting the text.
        return ReasoningResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            stop_category=stop_category,
            usage=usage,
            raw=resp,
        )
