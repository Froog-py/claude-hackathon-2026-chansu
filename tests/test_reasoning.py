"""Reasoning-layer tests: the model-adapter contract and the Claude backend's mapping.

The Claude backend is exercised with an injected mock client, so these run with no
``anthropic`` install and no live API call — they lock the request/response mapping, the
refusal handling, and error normalization (PROJECT.md §6, §10).
"""

import types

import pytest

from chansu.reasoning.adapter import (
    ClaudeReasoningModel,
    EchoReasoningModel,
    Message,
    ReasoningError,
    ReasoningModel,
    ReasoningRequest,
    ReasoningTimeout,
    ToolSpec,
)


def _fake_client(create):
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def test_echo_stub_conforms_to_the_interface():
    model = EchoReasoningModel()
    assert isinstance(model, ReasoningModel)  # runtime-checkable Protocol
    resp = model.complete(ReasoningRequest(system="s", messages=[Message("user", "ping")]))
    assert resp.text == "[echo] ping" and resp.stop_reason == "end_turn"


def test_claude_adapter_maps_request_and_response():
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            content=[
                types.SimpleNamespace(type="text", text="ethanol has..."),
                types.SimpleNamespace(type="tool_use", id="tu_1", name="get_props", input={"smiles": "CCO"}),
            ],
            stop_reason="tool_use",
            usage=types.SimpleNamespace(input_tokens=12, output_tokens=7),
        )

    model = ClaudeReasoningModel(client=_fake_client(create))
    assert isinstance(model, ReasoningModel)

    resp = model.complete(
        ReasoningRequest(
            system="You are a medicinal chemist.",
            messages=[Message("user", "properties for ethanol?")],
            tools=[ToolSpec("get_props", "compute properties", {"type": "object", "properties": {}})],
            max_tokens=1024,
            temperature=0.7,  # must NOT be forwarded (Opus 4.8 rejects sampling params)
        )
    )

    # request mapping
    assert captured["model"] == "claude-opus-4-8"
    assert captured["max_tokens"] == 1024
    assert captured["system"] == "You are a medicinal chemist."
    assert captured["messages"] == [{"role": "user", "content": "properties for ethanol?"}]
    assert captured["tools"][0]["name"] == "get_props"
    assert captured["thinking"] == {"type": "adaptive"}
    assert "temperature" not in captured  # sampling params omitted

    # response mapping
    assert resp.text == "ethanol has..."
    assert resp.stop_reason == "tool_use"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "get_props"
    assert resp.tool_calls[0].arguments == {"smiles": "CCO"}
    assert resp.usage.input_tokens == 12 and resp.usage.output_tokens == 7


def test_claude_adapter_surfaces_refusal_without_faking_completion():
    resp = ClaudeReasoningModel(
        client=_fake_client(lambda **k: types.SimpleNamespace(content=[], stop_reason="refusal", usage=None))
    ).complete(ReasoningRequest(system="", messages=[Message("user", "x")]))
    assert resp.stop_reason == "refusal" and resp.text == ""
    assert resp.stop_category is None  # no stop_details on this response -> read defensively


def test_claude_adapter_captures_refusal_category():
    """A refusal carries a category (``stop_details.category``, e.g. ``"bio"``) — surfaced first-class
    so the trust boundary can say *what* the model's safety layer declined, not just that it did."""
    resp = ClaudeReasoningModel(
        client=_fake_client(lambda **k: types.SimpleNamespace(
            content=[], stop_reason="refusal",
            stop_details=types.SimpleNamespace(category="bio"), usage=None,
        ))
    ).complete(ReasoningRequest(system="", messages=[Message("user", "x")]))
    assert resp.stop_reason == "refusal" and resp.stop_category == "bio"


def test_claude_adapter_normalizes_api_failure_to_reasoning_error():
    def boom(**kwargs):
        raise RuntimeError("connection reset")

    with pytest.raises(ReasoningError):
        ClaudeReasoningModel(client=_fake_client(boom)).complete(
            ReasoningRequest(system="", messages=[Message("user", "x")])
        )


def test_claude_adapter_maps_timeout_to_reasoning_timeout():
    """A request timeout must surface as ReasoningTimeout, not a generic ReasoningError — matched
    by type name so the optional SDK need not be installed to classify it (Codex P1)."""

    class APITimeoutError(Exception):  # mirrors anthropic.APITimeoutError by name
        pass

    def boom(**kwargs):
        raise APITimeoutError("deadline exceeded")

    with pytest.raises(ReasoningTimeout):
        ClaudeReasoningModel(client=_fake_client(boom)).complete(
            ReasoningRequest(system="", messages=[Message("user", "x")])
        )


def test_claude_adapter_rejects_malformed_response_instead_of_faking_success():
    """A response missing stop_reason/content is malformed — it must raise, never be promoted to
    an empty end_turn 'success' (Codex P1)."""
    with pytest.raises(ReasoningError):
        ClaudeReasoningModel(client=_fake_client(lambda **k: types.SimpleNamespace())).complete(
            ReasoningRequest(system="", messages=[Message("user", "x")])
        )


def test_claude_adapter_normalizes_malformed_tool_block_to_reasoning_error():
    """A tool_use block with undecodable input must raise ReasoningError, not a raw TypeError leak
    to the caller (Codex P1)."""
    resp = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="tool_use", id="t", name="n", input=None)],
        stop_reason="tool_use",
        usage=None,
    )
    with pytest.raises(ReasoningError):
        ClaudeReasoningModel(client=_fake_client(lambda **k: resp)).complete(
            ReasoningRequest(system="", messages=[Message("user", "x")])
        )


def test_claude_adapter_uses_default_max_tokens_when_request_unset():
    """max_tokens=None must resolve to the backend default (Codex P2: the old ``or`` made the
    constructor default unreachable)."""
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(content=[], stop_reason="end_turn", usage=None)

    ClaudeReasoningModel(client=_fake_client(create), default_max_tokens=2048).complete(
        ReasoningRequest(system="", messages=[Message("user", "x")])  # max_tokens left as None
    )
    assert captured["max_tokens"] == 2048


def test_claude_adapter_reports_missing_sdk_clearly():
    # No client injected + anthropic almost certainly not installed in the test env -> a clear
    # ReasoningError, not an opaque ImportError.
    pytest.importorskip  # noqa: B018 - ensure pytest is imported; harmless
    try:
        import anthropic  # noqa: F401
    except ImportError:
        with pytest.raises(ReasoningError):
            ClaudeReasoningModel().complete(ReasoningRequest(system="", messages=[Message("user", "x")]))
