"""Smoke test for the local reasoning adapter (handoff spec §6B)."""

from __future__ import annotations

import os
import sys

from chansu.reasoning.adapter import Message, ReasoningError, ReasoningRequest, ToolSpec
from chansu.reasoning.local_adapter import LocalReasoningModel


def main() -> int:
    base_url = os.environ.get("CHANSU_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    model = os.environ.get("CHANSU_LOCAL_MODEL")
    if not model:
        print("Set CHANSU_LOCAL_MODEL to the served model name.", file=sys.stderr)
        return 1

    adapter = LocalReasoningModel(base_url=base_url, model=model)

    resp = adapter.complete(
        ReasoningRequest(
            system="You are a medicinal chemist. Answer in one sentence.",
            messages=[
                Message(
                    "user",
                    "Why does capping a hydroxyl as an ester change solubility?",
                )
            ],
        )
    )
    assert resp.text.strip(), "expected non-empty reasoning text"
    print("reasoning OK:", resp.text[:120])

    resp = adapter.complete(
        ReasoningRequest(
            system="Use the tool to look up a property when asked.",
            messages=[Message("user", "Get the molecular weight of the parent compound.")],
            tools=[
                ToolSpec(
                    "get_mw",
                    "Molecular weight of the current compound",
                    {"type": "object", "properties": {}, "required": []},
                )
            ],
        )
    )
    assert resp.stop_reason in ("tool_use", "end_turn")
    print("tool path OK:", resp.stop_reason, resp.tool_calls)

    try:
        LocalReasoningModel(base_url="http://127.0.0.1:9/v1", model="x").complete(
            ReasoningRequest(system="", messages=[Message("user", "hi")])
        )
        print("FAIL: should have raised ReasoningError")
        return 1
    except ReasoningError as exc:
        print("error path OK:", type(exc).__name__, str(exc)[:120])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
