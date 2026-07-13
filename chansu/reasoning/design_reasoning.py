"""Reasoning over a finished design (PROJECT.md §4 step 5, §6, §10 layer 2).

This is where the reasoning model is actually *used at runtime* — the two call sites PROJECT.md
puts in the trust boundary as "reasons by analogy … writes the memo":

  1. **Strategy-match rationale** — for each actionable (liability, strategy) match, explain *why*
     the precedent-backed strategy is a relevant avenue.
  2. **Memo narrative** — a short synthesis of the whole design.

Two reasoning **depths**, selected by ``depth`` (see ``docs/reasoning-depth-design.md``):

  * ``"strategy"`` (Mode A, default — the safe floor): reason at the strategy ↔ liability-class ↔
    attachment-type ↔ precedent level, **compound-agnostic**. No compound identity, no importance-map
    specifics. This is the reasoning's natural altitude (the library keys on class + type, §7), it
    keeps the request free of the compound-specific detail that trips safety classifiers, and it is
    reusable/cacheable across compounds. Not a dodge — the correct altitude.
  * ``"compound"`` (Mode B, opt-in): the richer compound-specific prompts. Each call is attempted
    compound-first and **falls back to strategy-level** on a refusal/unusable output
    (B → A → the deterministic memo, which needs no model at all). Never a dead end.

Everything the model sees is already deterministic and provenance-tagged: matching, generation,
gating, and scoring happen in the core (RDKit + the strategy library) and are *inputs* here. The
model synthesizes and explains; it never decides a match, moves the gate, touches a number, or
predicts an outcome. It introduces no new facts and no citations.

Model-agnostic by construction: this module depends only on the ``ReasoningModel`` *interface*.
Claude is what sits behind it today; swapping in another model is an adapter/config change, not a
change here. If no backend is configured, the first call fails cleanly and ``reason_over_design``
returns ``available=False`` — the memo stays deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.models import Compound
from ..core.pipeline import DesignResult
from .adapter import Message, ReasoningError, ReasoningModel, ReasoningRequest

# The adapter runs Opus 4.8 with adaptive thinking, and thinking tokens count against max_tokens. At
# the request default (4096) thinking can exhaust the budget before the visible answer, returning
# stop_reason="max_tokens" with empty text. 16000 is the reference's documented non-streaming
# default: ample room for thinking plus the short rationale/narrative, with no need to stream.
_REASONING_MAX_TOKENS = 16000

_SYSTEM = (
    "You are a reasoning aid for legitimate academic and pharmaceutical medicinal chemistry — the "
    "standard, published science of drug development — operating inside a tool with a strict trust "
    "boundary. The task is to help a medicinal chemist take a compound that has known therapeutic "
    "activity (for example anti-cancer or antiviral) but a liability that blocks its use as a medicine "
    "(toxicity, poor solubility, rapid clearance) and REDUCE that liability using established, "
    "approved-drug-precedented strategies (prodrugs, soft drugs, targeted delivery), so the compound "
    "can become a SAFER, usable therapeutic. Every strategy and precedent provided is drawn from the "
    "peer-reviewed literature. You reason BY ANALOGY from a documented, cited precedent to explain WHY "
    "a modification strategy is a relevant avenue for a given liability.\n\n"
    "Hard rules:\n"
    "- Do NOT predict binding affinity, toxicity, or efficacy, and never say a liability is "
    "'solved'. You explain reasoning; you do not forecast outcomes.\n"
    "- Ground every statement in the facts provided in the message. Introduce no external facts and "
    "invent no citations or numbers.\n"
    "- A high-importance region is FLAGGED, not forbidden — if the strategy acts there, name it as a "
    "deliberate, risk-acknowledged tuning move, not an error.\n"
    "- Be concise and specific. You are one input to a chemist's judgment, not a replacement for it."
)


@dataclass
class ReasoningCheck:
    """One reasoning call's outcome, recorded so the memo/UI can show every check pass/fail/why —
    never a silent omission (PROJECT.md §6; Luke's transparency directive). ``passed`` is True only
    when the call produced genuinely usable text. For a decline, ``stop_reason`` + ``category`` name
    *what* was declined (e.g. ``refusal`` / ``bio`` — the model's own safety layer). ``label``
    identifies the call, e.g. ``"synthesis"`` or ``"rationale:soft_drug_self_inactivation"``, with a
    ``[compound]`` / ``[strategy]`` / ``[strategy-fallback]`` suffix naming the depth attempted."""

    label: str
    passed: bool
    stop_reason: str
    category: Optional[str] = None
    output_tokens: Optional[int] = None


@dataclass
class DesignReasoning:
    """The model's runtime reasoning over a ``DesignResult``. ``model_name`` is the adapter's model
    id — what the ``[reasoning — <model_name>]`` provenance tag names. ``depth`` records which mode
    produced the rationales (``"strategy"`` or ``"compound"``). ``note`` carries an honest aside — a
    fallback ("compound-specific declined; showing strategy-level") or a diagnostic when nothing
    rendered — and ``available`` is False only when no backend is configured. ``checks`` records every
    reasoning call's pass/decline/why so the memo and UI can surface them transparently."""

    model_name: str
    available: bool = True
    depth: str = "strategy"
    narrative: Optional[str] = None
    # (liability_kind, strategy_id) -> rationale text
    rationales: dict = field(default_factory=dict)
    note: Optional[str] = None
    checks: list = field(default_factory=list)   # list[ReasoningCheck], in call order

    def rationale_for(self, liability_kind: str, strategy_id: str) -> Optional[str]:
        return self.rationales.get((liability_kind, strategy_id))

    def declined_checks(self) -> list:
        """The reasoning calls the backend declined or returned unusable — what the transparency
        panel highlights. B→A fallbacks that later succeeded still appear (their compound-level
        attempt was declined), so this is the honest count of what the model would not do."""
        return [c for c in self.checks if not c.passed]


@dataclass
class _MatchFacts:
    strategy: object                     # Strategy
    liability_kind: str
    positions: list                      # position labels acted on
    high_importance: list                # labels of positions in a high-importance region


def _usable_text(resp) -> Optional[str]:
    """Accept model text only when it is a genuinely complete answer. A refusal, a truncation, or
    empty text yields None — honest silence, never a faked rationale (PROJECT.md §6)."""
    if resp.stop_reason in ("end_turn", "stop_sequence") and resp.text.strip():
        return resp.text.strip()
    return None


def _liability_detail(compound: Compound, kind: str) -> str:
    for lib in compound.liabilities:
        if lib.kind == kind:
            return lib.detail or ""
    return ""


def _actionable_groups(result: DesignResult) -> dict:
    """Group candidates into actionable (liability, strategy) matches — those proposed at a real
    position. Positionless "no attachment point" candidates are left to the deterministic note (no
    analogy to draw)."""
    groups: dict = {}
    for c in result.candidates:
        if c.position_id is None:
            continue
        key = (c.liability, c.strategy.id)
        facts = groups.get(key)
        if facts is None:
            facts = _MatchFacts(strategy=c.strategy, liability_kind=c.liability, positions=[], high_importance=[])
            groups[key] = facts
        if c.position_label and c.position_label not in facts.positions:
            facts.positions.append(c.position_label)
        if any(f.code == "high_importance_region" for f in c.flags) and c.position_label not in facts.high_importance:
            facts.high_importance.append(c.position_label)
    return groups


def _importance_lines(compound: Compound) -> str:
    if not compound.importance_map:
        return "  (none curated)"
    return "\n".join(
        f"  - [{r.importance}] {r.locator.label or r.id}: {r.reason}" for r in compound.importance_map
    )


# --- Mode A: strategy-level, compound-agnostic (the default / safe floor) --------------------

def _rationale_request_strategy(facts: _MatchFacts) -> ReasoningRequest:
    """Strategy-level rationale: the strategy ↔ liability-class ↔ precedent relationship, with no
    compound identity or importance-map specifics. This is the reasoning's natural altitude and keeps
    the request free of the compound-specific detail that trips safety classifiers; it is also
    reusable across every compound with this liability+strategy."""
    s = facts.strategy
    cite = s.citation
    attach = ", ".join(s.attachment_types) or "(unspecified)"
    user = (
        f"Medicinal-chemistry strategy: {s.id}\n"
        f"  Concept: {s.concept}\n"
        f"  Mechanism: {s.mechanism}\n"
        f"  Precedent drug: {s.precedent_drug}\n"
        f"  Precedent citation: {cite.label} ({cite.source})\n\n"
        f"Liability class it addresses: {facts.liability_kind}\n"
        f"Attachment-point type(s) it requires: {attach}\n\n"
        "In 2–4 sentences, explain by analogy from the precedent why this strategy is a relevant avenue "
        "for a compound whose liability is of this class and which offers a compatible attachment point. "
        "Keep it about the medicinal-chemistry principle; do not name or assume any specific compound. "
        "Do not predict binding, toxicity, or efficacy."
    )
    return ReasoningRequest(system=_SYSTEM, messages=[Message("user", user)], max_tokens=_REASONING_MAX_TOKENS)


def _narrative_request_strategy(compound: Compound, result: DesignResult) -> ReasoningRequest:
    """Strategy-level synthesis: the avenues, scores, and trade-offs — without naming the compound."""
    lines = [
        "Synthesize a short design-memo paragraph for a compound with the following liabilities and "
        "matched strategies.",
        "",
        "Avenues found, per liability class:",
    ]
    lines += _avenue_lines(compound, result)
    lines += [
        "",
        "In one tight paragraph, synthesize which avenues were surfaced, the trade-offs the transparent "
        "scores highlight, which proposed edits touch essential regions (flagged, not forbidden), and "
        "what remains for wet-lab validation. Keep it about the strategies and their trade-offs; do not "
        "name or assume a specific compound. Do not predict binding, toxicity, or efficacy; do not claim "
        "any liability is solved.",
    ]
    return ReasoningRequest(system=_SYSTEM, messages=[Message("user", "\n".join(lines))], max_tokens=_REASONING_MAX_TOKENS)


# --- Mode B: compound-specific (opt-in; richer, trips classifiers on sensitive compounds) ----

def _rationale_request_compound(compound: Compound, facts: _MatchFacts) -> ReasoningRequest:
    s = facts.strategy
    cite = s.citation
    high = ", ".join(facts.high_importance) if facts.high_importance else "none"
    user = (
        f"Compound: {compound.name}"
        + (f" (class: {compound.annotations['class']})" if compound.annotations.get("class") else "")
        + "\n"
        f"Liability to address: {facts.liability_kind} — {_liability_detail(compound, facts.liability_kind)}\n\n"
        f"Candidate strategy: {s.id}\n"
        f"  Concept: {s.concept}\n"
        f"  Mechanism: {s.mechanism}\n"
        f"  Precedent drug: {s.precedent_drug}\n"
        f"  Precedent citation: {cite.label} ({cite.source})\n\n"
        f"Position(s) it would act on: {', '.join(facts.positions) or '(unspecified)'}\n"
        f"Of those, in a high-importance region: {high}\n\n"
        f"Graded importance map (advisory):\n{_importance_lines(compound)}\n\n"
        "In 2–4 sentences, explain why this precedent-backed strategy is a relevant avenue for this "
        "liability on this compound, reasoning by analogy from the precedent. Reference the specific "
        "position(s) it acts on. If it edits a high-importance region, say so plainly as a deliberate "
        "tuning move, not a mistake. Do not predict binding, toxicity, or efficacy."
    )
    return ReasoningRequest(system=_SYSTEM, messages=[Message("user", user)], max_tokens=_REASONING_MAX_TOKENS)


def _narrative_request_compound(compound: Compound, result: DesignResult) -> ReasoningRequest:
    lines = [f"Write a short design-memo synthesis for {compound.name}.", "", "Avenues found, per liability:"]
    lines += _avenue_lines(compound, result)
    lines += [
        "",
        "In one tight paragraph, synthesize: which avenues the tool surfaced, the trade-offs the "
        "transparent scores highlight, which proposed edits touch essential regions (flagged for the "
        "chemist, not forbidden), and what remains for wet-lab validation. Do not predict binding, "
        "toxicity, or efficacy; do not claim any liability is solved.",
    ]
    return ReasoningRequest(system=_SYSTEM, messages=[Message("user", "\n".join(lines))], max_tokens=_REASONING_MAX_TOKENS)


def _avenue_lines(compound: Compound, result: DesignResult) -> list:
    """The per-liability avenue list shared by both narrative depths (strategy ids + scores + flags;
    benign — no compound name or toxin framing here)."""
    by_liability: dict = {}
    for c in result.candidates:
        by_liability.setdefault(c.liability, []).append(c)
    lines = []
    for lib in compound.liabilities:
        if any(u.kind == lib.kind for u in result.unaddressed):
            lines.append(f"- {lib.kind}: no precedented strategy in the current library (honest failure).")
            continue
        parts = []
        for c in by_liability.get(lib.kind, []):
            where = f" at {c.position_label}" if c.position_label else ""
            if c.analog.valid and c.score is not None:
                flagged = " [flagged: high-importance region]" if any(
                    f.code == "high_importance_region" for f in c.flags
                ) else ""
                parts.append(f"{c.strategy.id}{where} (score {c.score.total}){flagged}")
            else:
                parts.append(f"{c.strategy.id}{where} (describe-only)")
        lines.append(f"- {lib.kind}: " + ("; ".join(parts) if parts else "no actionable candidate"))
    return lines


def reason_over_design(
    compound: Compound, result: DesignResult, model: ReasoningModel, depth: str = "strategy"
) -> DesignReasoning:
    """Ask ``model`` (through the interface) for the memo narrative and a per-match rationale, at the
    requested ``depth`` (``"strategy"`` default, or ``"compound"``). For ``"compound"``, each call is
    attempted compound-first and **falls back to strategy-level** on a refusal/unusable output
    (B → A → the deterministic memo). The first call doubles as the availability probe: if the backend
    is down, this returns ``available=False`` and the caller renders the deterministic memo.

    A 200 whose text is unusable (a refusal, a truncation, an empty completion) is honest silence — its
    ``stop_reason`` + token usage is captured so a memo that renders nothing still says *why*."""
    model_name = model.name
    diagnostics: list = []
    checks: list = []
    fell_back = False

    def _try(request, label: str) -> Optional[str]:
        resp = model.complete(request)
        text = _usable_text(resp)
        out = resp.usage.output_tokens if resp.usage else None
        checks.append(ReasoningCheck(
            label=label, passed=text is not None, stop_reason=resp.stop_reason,
            category=resp.stop_category, output_tokens=out,
        ))
        if text is None:  # a 200 we can't use — record why, for the memo's diagnostic line
            cat = f"/{resp.stop_category}" if resp.stop_category else ""
            diagnostics.append(
                f"{label}: stop_reason={resp.stop_reason}{cat} "
                f"output_tokens={out if out is not None else '?'} text_len={len(resp.text)}"
            )
        return text

    def _reason(build_compound, build_strategy, label: str) -> Optional[str]:
        nonlocal fell_back
        if depth == "compound":
            text = _try(build_compound(), f"{label}[compound]")
            if text:
                return text
            fell_back = True  # B declined -> fall back to A
            return _try(build_strategy(), f"{label}[strategy-fallback]")
        return _try(build_strategy(), f"{label}[strategy]")

    try:
        narrative = _reason(
            lambda: _narrative_request_compound(compound, result),
            lambda: _narrative_request_strategy(compound, result),
            "synthesis",
        )
    except ReasoningError as exc:
        return DesignReasoning(
            model_name=model_name, available=False, depth=depth, note=f"reasoning backend unavailable: {exc}"
        )

    rationales: dict = {}
    for key, facts in _actionable_groups(result).items():
        try:
            text = _reason(
                (lambda f=facts: _rationale_request_compound(compound, f)),
                (lambda f=facts: _rationale_request_strategy(f)),
                f"rationale:{key[1]}",
            )
        except ReasoningError:
            continue  # a single flaky call must not sink the memo; skip just this rationale
        if text:
            rationales[key] = text

    note = None
    if fell_back and (narrative or rationales):
        note = "compound-specific reasoning was declined by the model; showing strategy-level reasoning instead."
    elif not narrative and not rationales and diagnostics:
        note = "backend responded but returned no usable text — " + " | ".join(diagnostics[:3])
    return DesignReasoning(
        model_name=model_name, available=True, depth=depth, narrative=narrative,
        rationales=rationales, note=note, checks=checks,
    )
