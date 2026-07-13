"""Tests for the OpenAI-compatible reasoning adapter (request/response mapping against an injected
fake client, so no network or SDK is exercised)."""
import pytest

from chansu.reasoning.adapter import Message, ReasoningError, ReasoningRequest
from chansu.reasoning.openai_compatible import OpenAICompatibleReasoningModel


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish):
        self.message = _Msg(content)
        self.finish_reason = finish


class _Usage:
    def __init__(self, p, c):
        self.prompt_tokens = p
        self.completion_tokens = c


class _Resp:
    def __init__(self, content="hi", finish="stop", usage=(10, 5)):
        self.choices = [_Choice(content, finish)]
        self.usage = _Usage(*usage) if usage else None


class _Completions:
    def __init__(self, resp, spy=None):
        self._resp = resp
        self._spy = spy

    def create(self, **kwargs):
        if self._spy is not None:
            self._spy.update(kwargs)
        return self._resp


class _Chat:
    def __init__(self, resp, spy=None):
        self.completions = _Completions(resp, spy)


class _Client:
    def __init__(self, resp, spy=None):
        self.chat = _Chat(resp, spy)


def _model(resp, spy=None):
    return OpenAICompatibleReasoningModel(model="m", base_url="http://x/v1", client=_Client(resp, spy))


def _req():
    return ReasoningRequest(system="SYS", messages=[Message("user", "U")], max_tokens=32)


def test_maps_text_and_stop_and_usage():
    r = _model(_Resp("answer", "stop", (7, 3))).complete(_req())
    assert r.text == "answer"
    assert r.stop_reason == "end_turn"  # openai "stop" -> interface "end_turn"
    assert r.usage.input_tokens == 7 and r.usage.output_tokens == 3


def test_finish_reason_mapping():
    assert _model(_Resp(finish="length")).complete(_req()).stop_reason == "max_tokens"
    assert _model(_Resp(finish="content_filter")).complete(_req()).stop_reason == "refusal"


def test_system_prompt_becomes_first_message():
    spy = {}
    _model(_Resp(), spy).complete(_req())
    assert spy["messages"][0] == {"role": "system", "content": "SYS"}
    assert spy["model"] == "m" and spy["max_tokens"] == 32


def test_name_is_the_model_id():
    assert _model(_Resp()).name == "m"


def test_missing_key_raises_reasoning_error():
    m = OpenAICompatibleReasoningModel(model="m", base_url="http://x/v1", api_key_env="DEFINITELY_UNSET_XYZ")
    with pytest.raises(ReasoningError):
        m._api_key()
