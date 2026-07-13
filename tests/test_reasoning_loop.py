"""The reasoning loop wired through the adapter (PROJECT.md §4 step 5, §6, §10 layer 2).

Claude drives the two runtime reasoning outputs — the strategy-match rationale and the memo
narrative — but *through the ReasoningModel interface*. These tests run with injected mock clients
(no ``anthropic`` install, no live call), so they lock: the model is reached through the interface,
the prompts are grounded in the deterministic result, the reasoning is provenance-tagged with the
model's name, and everything degrades honestly when the backend is unavailable or refuses.
"""

import types

import pytest

from chansu.core.loaders import load_compound, load_strategies, to_mol
from chansu.core.models import Provenance, reasoning_tag, tag
from chansu.core.pipeline import design
from chansu.reasoning.adapter import ClaudeReasoningModel, EchoReasoningModel, ReasoningModel
from chansu.reasoning.design_reasoning import DesignReasoning, ReasoningCheck, reason_over_design
from chansu.report import render_memo


def _bufalin_design():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    return compound, mol, design(compound, mol, load_strategies())


def _fake_client(create):
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def _canned_client(captured):
    """A mock Anthropic client: records each request and returns distinguishable text for the
    narrative vs. a rationale so the test can prove each lands in the right place."""

    def create(**kwargs):
        captured.append(kwargs)
        user = kwargs["messages"][-1]["content"]
        # narratives ask to "synthesize"; rationales ask to "explain" — works for both depths
        text = "SYNTHESIS_NARRATIVE" if "synthesize" in user.lower() else "RATIONALE_TEXT"
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            usage=None,
        )

    return _fake_client(create)


# --- provenance vocabulary -------------------------------------------------------------------

def test_reasoning_tag_names_the_model_and_is_structurally_enforced():
    assert reasoning_tag("claude-opus-4-8") == "[reasoning · claude-opus-4-8]"
    assert reasoning_tag("qwen2.5") == "[reasoning · qwen2.5]"  # no hardcoded vendor
    for blank in ("", "   ", "\n"):
        with pytest.raises(ValueError):
            reasoning_tag(blank)  # no model, no tag — same enforcement as [literature · cited]
    with pytest.raises(ValueError):
        tag(Provenance.REASONING)  # reasoning names its model; the fixed-string tag() rejects it


def test_model_name_flows_from_the_adapter():
    assert ClaudeReasoningModel(model="claude-opus-4-8").name == "claude-opus-4-8"
    assert ClaudeReasoningModel(model="some-other-model").name == "some-other-model"
    assert EchoReasoningModel().name == "echo"
    # adding `name` to the interface must not break the runtime-checkable Protocol
    assert isinstance(EchoReasoningModel(), ReasoningModel)
    assert isinstance(ClaudeReasoningModel(), ReasoningModel)


# --- the orchestrator, through the interface -------------------------------------------------

def test_default_depth_is_strategy_level_and_compound_agnostic():
    """The default depth is strategy-level (Mode A): the model reasons about the strategy /
    liability-class / precedent relationship, and the prompt NEVER names the compound — that's what
    keeps it clear of the bio safety classifier and reusable across compounds."""
    compound, _, result = _bufalin_design()
    captured: list = []
    reasoning = reason_over_design(compound, result, ClaudeReasoningModel(client=_canned_client(captured)))

    assert reasoning.available and reasoning.depth == "strategy"
    assert reasoning.model_name == "claude-opus-4-8"
    assert reasoning.narrative == "SYNTHESIS_NARRATIVE"
    assert reasoning.rationale_for("systemic_toxicity", "soft_drug_self_inactivation") == "RATIONALE_TEXT"
    assert ("poor_selectivity", "glycosylation_isoform_selectivity") in reasoning.rationales
    assert ("poor_solubility", "ester_prodrug_pk_masking") not in reasoning.rationales  # no attachment point

    assert captured and all("Do NOT predict" in k["system"] for k in captured)   # trust-boundary system prompt
    assert all(k["max_tokens"] >= 16000 for k in captured)                        # budget headroom for thinking
    # NO prompt names the compound — Mode A is compound-agnostic by construction
    assert all("Bufalin" not in k["messages"][-1]["content"] for k in captured)

    # the soft-drug strategy-level prompt is grounded in the precedent + liability CLASS + attachment
    # TYPE, and carries no compound-specific positions (those are deterministic, rendered by the engine)
    soft = next(
        k["messages"][-1]["content"] for k in captured
        if "Medicinal-chemistry strategy: soft_drug_self_inactivation" in k["messages"][-1]["content"]
    )
    assert "Fluticasone" in soft and "systemic_toxicity" in soft and "hydroxyl" in soft
    assert "C3 secondary hydroxyl" not in soft  # compound-specific position stays out of Mode A


def test_depth_compound_uses_compound_specific_prompts():
    """Opt-in Mode B names the compound and its exact positions (richer, but trips classifiers)."""
    compound, _, result = _bufalin_design()
    captured: list = []
    reason_over_design(
        compound, result, ClaudeReasoningModel(client=_canned_client(captured)), depth="compound"
    )
    soft = next(
        k["messages"][-1]["content"] for k in captured
        if "Candidate strategy: soft_drug_self_inactivation" in k["messages"][-1]["content"]
    )
    assert "Bufalin" in soft and "Fluticasone" in soft
    assert "C3 secondary hydroxyl" in soft and "C14 tertiary hydroxyl" in soft


def test_mode_b_declines_falls_back_to_mode_a():
    """The critical path: depth='compound' but the model refuses the compound-specific prompts (the
    bufalin case). Each call must fall back to strategy-level, the memo must still carry rationales,
    and the note must say the compound-specific pass was declined."""
    compound, mol, result = _bufalin_design()
    captured: list = []

    def create(**kwargs):
        captured.append(kwargs)
        user = kwargs["messages"][-1]["content"]
        if "Bufalin" in user:  # simulate the bio classifier: refuse compound-specific, allow strategy-level
            return types.SimpleNamespace(
                content=[], stop_reason="refusal",
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        text = "STRAT_SYNTH" if "synthesize" in user.lower() else "STRAT_RATIONALE"
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=text)], stop_reason="end_turn", usage=None
        )

    reasoning = reason_over_design(
        compound, result, ClaudeReasoningModel(client=_fake_client(create)), depth="compound"
    )

    assert reasoning.available and reasoning.depth == "compound"
    assert reasoning.rationale_for("systemic_toxicity", "soft_drug_self_inactivation") == "STRAT_RATIONALE"
    assert reasoning.narrative == "STRAT_SYNTH"
    assert reasoning.note and "declined" in reasoning.note and "strategy-level" in reasoning.note

    prompts = [k["messages"][-1]["content"] for k in captured]
    assert any("Candidate strategy: soft_drug_self_inactivation" in p and "Bufalin" in p for p in prompts)  # B attempt
    assert any("Medicinal-chemistry strategy: soft_drug_self_inactivation" in p for p in prompts)           # A fallback

    memo = render_memo(compound, mol, result, reasoning)
    assert "Reasoning mode: compound-specific" in memo
    assert "declined" in memo and "STRAT_RATIONALE" in memo


def test_every_reasoning_call_is_recorded_as_a_check_with_why():
    """Transparency (PROJECT.md §6): every reasoning call is recorded pass/decline + why, so a memo
    that shows the cleared rationales never silently omits the declined ones. A decline carries the
    model's own safety category (e.g. ``bio``)."""
    compound, _, result = _bufalin_design()

    def create(**kwargs):
        user = kwargs["messages"][-1]["content"]
        if "synthesize" in user.lower():  # decline the narrative like the real bio classifier
            return types.SimpleNamespace(
                content=[], stop_reason="refusal",
                stop_details=types.SimpleNamespace(category="bio"),
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="RATIONALE")], stop_reason="end_turn", usage=None
        )

    reasoning = reason_over_design(compound, result, ClaudeReasoningModel(client=_fake_client(create)))

    assert reasoning.checks, "every reasoning call must be recorded"
    narrative_check = next(c for c in reasoning.checks if c.label.startswith("synthesis"))
    assert not narrative_check.passed
    assert narrative_check.stop_reason == "refusal" and narrative_check.category == "bio"
    assert any(c.passed for c in reasoning.checks)          # the rationales cleared
    declined = reasoning.declined_checks()
    assert declined and all(c.category == "bio" for c in declined)  # the honest count, by category


def test_memo_surfaces_declined_reasoning_checks_not_just_the_cleared_ones():
    """The resume-cursor fix: with some rationales cleared and one declined, the memo reports
    'N of M calls passed; K declined ... (bio)' and lists the declined call — never silent omission."""
    compound, mol, result = _bufalin_design()
    reasoning = DesignReasoning(
        model_name="claude-opus-4-8", available=True,
        narrative="SYNTH",
        rationales={("systemic_toxicity", "soft_drug_self_inactivation"): "R"},
        checks=[
            ReasoningCheck("synthesis[strategy]", True, "end_turn"),
            ReasoningCheck("rationale:soft_drug_self_inactivation[strategy]", True, "end_turn"),
            ReasoningCheck("rationale:glycosylation_isoform_selectivity[strategy]", False, "refusal", "bio", 1),
        ],
    )
    memo = render_memo(compound, mol, result, reasoning)
    assert "Reasoning checks: 2 of 3 calls passed" in memo
    assert "1 declined" in memo and "bio" in memo
    assert "glycosylation_isoform_selectivity[strategy]: declined (refusal/bio" in memo


def test_reason_over_design_degrades_when_backend_is_unavailable():
    compound, _, result = _bufalin_design()

    def boom(**kwargs):
        raise RuntimeError("no API key configured")

    reasoning = reason_over_design(compound, result, ClaudeReasoningModel(client=_fake_client(boom)))
    assert not reasoning.available
    assert reasoning.model_name == "claude-opus-4-8"  # known from config even when the call fails
    assert reasoning.narrative is None and reasoning.rationales == {}
    assert reasoning.note and "unavailable" in reasoning.note


def test_refusal_is_not_laundered_into_reasoning():
    """A 200 refusal (backend up, model declined) yields honest silence — never faked reasoning,
    and the stop_reason is captured so the memo can say why nothing rendered."""
    compound, _, result = _bufalin_design()
    refuse = _fake_client(lambda **k: types.SimpleNamespace(content=[], stop_reason="refusal", usage=None))
    reasoning = reason_over_design(compound, result, ClaudeReasoningModel(client=refuse))
    assert reasoning.available            # the backend responded
    assert reasoning.narrative is None    # refusal -> not used as a synthesis
    assert reasoning.rationales == {}     # every rationale refusal skipped, none fabricated
    assert reasoning.note and "refusal" in reasoning.note  # the cause is diagnosable, not silent


def test_truncated_response_is_diagnosed_not_silently_dropped():
    """A max_tokens truncation (adaptive thinking exhausted the budget before the visible answer)
    returns a 200 with no usable text — exactly the live-smoke-test failure. The memo must report
    the stop_reason + token usage so the cause is diagnosable, not a bare 'no synthesis'."""
    compound, mol, result = _bufalin_design()
    truncated = _fake_client(lambda **k: types.SimpleNamespace(
        content=[types.SimpleNamespace(type="thinking", thinking="")],  # all budget went to thinking
        stop_reason="max_tokens",
        usage=types.SimpleNamespace(input_tokens=200, output_tokens=16000),
    ))
    reasoning = reason_over_design(compound, result, ClaudeReasoningModel(client=truncated))
    assert reasoning.available and reasoning.narrative is None and reasoning.rationales == {}
    assert reasoning.note and "max_tokens" in reasoning.note and "output_tokens=16000" in reasoning.note

    memo = render_memo(compound, mol, result, reasoning)
    assert "diagnostic:" in memo and "max_tokens" in memo  # the memo self-reports the cause


# --- rendering the reasoning in the memo -----------------------------------------------------

def test_memo_renders_reasoning_tagged_with_the_model():
    compound, mol, result = _bufalin_design()
    reasoning = DesignReasoning(
        model_name="claude-opus-4-8",
        available=True,
        narrative="THE_SYNTHESIS_PARAGRAPH",
        rationales={("systemic_toxicity", "soft_drug_self_inactivation"): "THE_RATIONALE_TEXT"},
    )
    memo = render_memo(compound, mol, result, reasoning)

    assert "[reasoning · claude-opus-4-8]" in memo               # tagged, names the model
    assert "Reasoning mode: strategy-level" in memo              # depth surfaced to the reader
    assert "Why soft_drug_self_inactivation applies" in memo
    assert "THE_RATIONALE_TEXT" in memo
    assert "Design synthesis" in memo and "THE_SYNTHESIS_PARAGRAPH" in memo
    # the precedent still carries its own cited tag, separate from the reasoning tag
    assert "[literature · cited]" in memo


def test_memo_without_reasoning_is_the_deterministic_memo():
    """reasoning=None (no backend attempted) must reproduce the deterministic memo exactly —
    backward compatible, no reasoning surfaces at all."""
    compound, mol, result = _bufalin_design()
    memo = render_memo(compound, mol, result)  # reasoning omitted
    assert "DESIGN MEMO" in memo
    assert "[reasoning ·" not in memo
    assert "Design synthesis" not in memo


def test_memo_notes_when_reasoning_was_not_run():
    compound, mol, result = _bufalin_design()
    reasoning = DesignReasoning(model_name="claude-opus-4-8", available=False, note="reasoning backend unavailable: no key")
    memo = render_memo(compound, mol, result, reasoning)
    assert "reasoning not run" in memo and "no key" in memo
    assert "[reasoning ·" not in memo  # nothing claims to be model reasoning when none ran
