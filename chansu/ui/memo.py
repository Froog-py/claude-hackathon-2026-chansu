"""Design-memo screen (spec: "Screen 2 · Design memo"; chansu-design skill).

Renders the deterministic design as styled components: the scoring rubric, the per-liability candidates
with their score, property deltas, and gate flags, and the reasoning synthesis. Content and provenance
are faithful to ``report.render_memo`` (no claim invented or dropped); the byte-exact plain-text memo
stays available behind an expander.

Every claim carries a ``.cs-prov`` tag (computed / literature / reasoning / hypothesis / uncited).
Chemistry is wrapped with ``chem``/``sci``/``formula``. Machine data (identifiers, deltas) is mono.
Declines and honest failures are the calm ``.cs-declined`` state, never the flag register. Voice follows
the scientific register: terse, hedged by provenance. This module arranges and displays only.
"""

from __future__ import annotations

import html

import streamlit as st

from ..core.properties import compute_properties
from ..reasoning.adapter import ReasoningError
from ..reasoning.design_reasoning import reason_over_design
from ..report import render_memo
from . import state
from .notation import chem, formula, sci

_PROV_LABEL = {"computed": "computed", "lit": "literature · cited", "hyp": "hypothesis", "uncited": "uncited"}


def _prov(kind: str) -> str:
    return f"<span class='cs-prov {kind}'>{_PROV_LABEL[kind]}</span>"


def _prov_reason(model_name: str) -> str:
    return f"<span class='cs-prov reason'>reasoning · {html.escape(model_name)}</span>"


def _human(identifier: str) -> str:
    """A data identifier (a liability kind, a strategy id) as a readable interface name."""
    return identifier.replace("_", " ").strip().capitalize()


def _delta(value: float, parent: float, places: int = 2) -> str:
    """A property value with its signed change from the parent, mono, no semantic colour (a delta is
    neither brand nor data-palette meaning). ``places`` matches the workspace stat strip's precision."""
    d = round(value - parent, places)
    sign = "+" if d >= 0 else ""
    return f"{value:.{places}f} <span style='color:var(--ink-3)'>({sign}{d:.{places}f})</span>"


# --- reasoning-checks panel (calm; declines are the trust boundary working) ------------------

def _render_checks(reasoning) -> None:
    if not reasoning.available:
        st.markdown(
            f"<div class='cs-declined'>Reasoning not run. {chem(reasoning.note or 'no backend configured', serif=False)}.</div>",
            unsafe_allow_html=True,
        )
        return
    checks = getattr(reasoning, "checks", None)
    if not checks:
        return
    passed = sum(1 for c in checks if c.passed)
    declined = [c for c in checks if not c.passed]
    cats = sorted({c.category for c in declined if c.category})
    head = f"{passed} of {len(checks)} reasoning calls cleared."
    if declined:
        head += f" {len(declined)} declined by the model's own safety layer" + (f" ({', '.join(cats)})." if cats else ".")
    st.markdown(f"<p class='cs-eyebrow'>Reasoning checks</p><div class='cs-sub'>{sci(head)}</div>", unsafe_allow_html=True)
    if declined:
        st.markdown(
            "<div class='cs-sub' style='margin:4px 0 8px'>Declines are shown, not hidden. The deterministic "
            "memo below loses nothing when the model declines.</div>",
            unsafe_allow_html=True,
        )
    rows = []
    for c in checks:
        if c.passed:
            rows.append(f"<div style='margin-top:4px;font-family:var(--font-mono);font-size:11px;color:var(--ink-2)'>"
                        f"<span style='color:var(--pass)'>cleared</span> · {html.escape(c.label)}</div>")
        else:
            why = c.stop_reason + (f"/{c.category}" if c.category else "")
            rows.append(f"<div style='margin-top:4px'><span class='cs-declined'>declined · {html.escape(why)}</span>"
                        f"<span style='font-family:var(--font-mono);font-size:11px;color:var(--ink-3);margin-left:8px'>{html.escape(c.label)}</span></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


# --- candidates ------------------------------------------------------------------------------

def _flags_html(flags) -> str:
    out = []
    for f in flags:
        if f.code == "high_importance_region":
            cite = f" {_prov('lit')}" if getattr(f, "citation", None) and f.citation.source else ""
            out.append(f"<div style='margin-top:8px'><span class='cs-flag'>flag</span>{chem(f.message, serif=False)}{cite}</div>")
            if f.overridden:
                out.append(f"<div class='cs-sub' style='margin-top:4px'>Overridden by chemist. "
                           f"Reason recorded: {html.escape(f.override_reason or '')}</div>")
            elif f.overridable:
                out.append("<div class='cs-sub' style='margin-top:4px'>Flagged, not blocked.</div>")
        else:
            out.append(f"<div class='cs-sub' style='margin-top:4px'>{chem(f.message, serif=False)}</div>")
    return "".join(out)


def _candidate_card(candidate, parent, index: int) -> None:
    s = candidate.strategy
    pos = f" at {chem(candidate.position_label, serif=True)}" if candidate.position_label else ""
    cite = _prov("lit") if (s.citation and s.citation.source) else _prov("uncited")
    src = f"<div class='cs-cite'>{html.escape(s.citation.source)}</div>" if (s.citation and s.citation.source) else ""
    head = f"<div class='t'>{index}. {html.escape(_human(s.id))}{pos}</div>"
    sub = f"<div class='cs-sub'>Precedent: {chem(s.precedent_drug, serif=False)}</div>{src}<div style='margin-top:4px'>{cite}</div>"

    analog = (f"<div style='font-family:var(--font-mono);font-size:12px;color:var(--ink-2);margin-top:12px;"
              f"word-break:break-all'>{html.escape(candidate.analog.product_smiles)}</div>"
              f"<div style='margin-top:4px'>{_prov('hyp')}</div>")

    sc = candidate.score
    score_line = (f"<div style='font-family:var(--font-mono);font-size:12px;color:var(--ink);margin-top:12px'>"
                  f"score {sc.total} = {sc.weights['similarity']}·{sc.similarity} + {sc.weights['ease']}·{sc.ease}"
                  f" + {sc.weights['druglikeness']}·{sc.druglikeness}</div>")
    p = candidate.properties
    delta_line = (f"<div style='font-family:var(--font-mono);font-size:12px;color:var(--ink-2);margin-top:4px'>"
                  f"{formula(p['formula'])} · MW {_delta(p['mw'], parent.mw, 1)} · logP {_delta(p['logp'], parent.logp, 2)}"
                  f" · TPSA {_delta(p['tpsa'], parent.tpsa, 1)}</div>"
                  f"<div style='margin-top:4px'>{_prov('computed')}</div>")

    st.markdown(f"<div class='cs-card'>{head}{sub}{analog}{score_line}{delta_line}{_flags_html(candidate.flags)}</div>",
                unsafe_allow_html=True)


def _described_card(candidate) -> None:
    s = candidate.strategy
    pos = f" at {chem(candidate.position_label, serif=True)}" if candidate.position_label else " (no compatible attachment point)"
    cite = _prov("lit") if (s.citation and s.citation.source) else _prov("uncited")
    src = f"<div class='cs-cite'>{html.escape(s.citation.source)}</div>" if (s.citation and s.citation.source) else ""
    st.markdown(
        f"<div class='cs-card'><div class='t'>{html.escape(_human(s.id))}{pos}</div>"
        f"<div class='cs-sub'>Precedent: {chem(s.precedent_drug, serif=False)}</div>{src}"
        f"<div style='margin-top:4px'>{cite}</div>"
        f"<div class='cs-sub' style='margin-top:12px'>{chem(candidate.analog.description, serif=False)}</div>"
        f"<div style='margin-top:4px'>{_prov('hyp')}</div>{_flags_html(candidate.flags)}</div>",
        unsafe_allow_html=True,
    )


def _liability_block(lib, group, reasoning, parent, unaddressed) -> None:
    lit = _prov("lit") if (lib.citation and lib.citation.source) else _prov("uncited")
    st.markdown(
        f"<div style='margin-top:16px'><span style='font-family:var(--font-mono);font-size:10.5px;"
        f"letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-3);margin-right:8px'>Liability</span>"
        f"<span style='font-weight:600;color:var(--ink)'>{html.escape(_human(lib.kind))}</span> {lit}</div>",
        unsafe_allow_html=True,
    )
    if lib.kind in unaddressed:
        st.markdown(
            "<div class='cs-declined' style='margin-top:8px'>No precedented strategy in the current library. "
            "The tool declines to over-claim.</div>",
            unsafe_allow_html=True,
        )
        return

    if reasoning is not None and reasoning.available:
        seen = set()
        for c in group:
            if c.strategy.id in seen:
                continue
            text = reasoning.rationale_for(lib.kind, c.strategy.id)
            if not text:
                continue
            seen.add(c.strategy.id)
            st.markdown(f"<div style='margin-top:8px'>{_prov_reason(reasoning.model_name)}</div>", unsafe_allow_html=True)
            st.markdown(sci(text.strip()))

    valid = sorted([c for c in group if c.analog.valid and c.score is not None], key=lambda c: c.score.total, reverse=True)
    for i, candidate in enumerate(valid, 1):
        _candidate_card(candidate, parent, i)
    for candidate in group:
        if candidate.analog.describe_only:
            _described_card(candidate)


def _synthesis(reasoning) -> None:
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    st.markdown("<p class='cs-eyebrow'>Design synthesis</p>", unsafe_allow_html=True)
    if not reasoning.available:
        st.markdown(
            f"<div class='cs-declined'>Reasoning not run. {chem(reasoning.note or '', serif=False)}. The deterministic design "
            "above stands on its own.</div>",
            unsafe_allow_html=True,
        )
        return
    mode = "compound-specific" if reasoning.depth == "compound" else "strategy-level, compound-agnostic"
    st.markdown(f"<div class='cs-sub'>Mode: {mode}.</div>", unsafe_allow_html=True)
    if reasoning.narrative:
        if reasoning.note:
            st.markdown(f"<div class='cs-sub' style='margin-top:4px'>{chem(reasoning.note, serif=False)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:8px'>{_prov_reason(reasoning.model_name)}</div>", unsafe_allow_html=True)
        st.markdown(sci(reasoning.narrative.strip()))
    else:
        note = f" {chem(reasoning.note, serif=False)}" if reasoning.note else ""
        st.markdown(f"<div class='cs-declined'>No synthesis for this run.{note}</div>", unsafe_allow_html=True)


def _memo_body(compound, mol, result, reasoning) -> None:
    parent = compute_properties(mol)

    st.markdown("<p class='cs-eyebrow'>Scoring rubric</p>", unsafe_allow_html=True)
    st.markdown(
        "<div class='cs-card'><div style='font-family:var(--font-mono);font-size:13px;color:var(--ink)'>"
        "score = 0.5·similarity + 0.25·ease + 0.25·druglikeness</div>"
        "<div class='cs-sub' style='margin-top:8px'>Weights are shown so the ranking is legible. Flags sit "
        f"beside the score, never folded into it.</div><div style='margin-top:8px'>{_prov('computed')}</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    st.markdown("<p class='cs-eyebrow'>Design candidates · per liability</p>", unsafe_allow_html=True)
    by_liability: dict = {}
    for c in result.candidates:
        by_liability.setdefault(c.liability, []).append(c)
    unaddressed = {lib.kind for lib in result.unaddressed}
    for lib in compound.liabilities:
        _liability_block(lib, by_liability.get(lib.kind, []), reasoning, parent, unaddressed)

    if reasoning is not None:
        _synthesis(reasoning)

    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    st.markdown("<p class='cs-eyebrow'>Validation and honest limits</p>", unsafe_allow_html=True)
    st.markdown(
        "<div class='cs-sub'>Candidates are grounded hypotheses. The tool does not predict binding, toxicity, "
        "or efficacy, and every candidate needs wet-lab validation. High-importance edits are flagged, not "
        "blocked. The chemist overrides with a recorded reason.</div>",
        unsafe_allow_html=True,
    )
    note = compound.annotations.get("validation_note")
    if note:
        st.markdown(
            f"<div class='cs-card' style='margin-top:12px'><div class='t'>Author's validation narrative "
            f"{_prov('uncited')}</div><div class='cs-sub'>Data-provided. Not verified against this run.</div>"
            f"<div class='cs-sub' style='margin-top:8px'>{chem(note, serif=False)}</div></div>",
            unsafe_allow_html=True,
        )


# --- the tab ---------------------------------------------------------------------------------

def _model_column(entry, reasoning, err) -> None:
    """One model's reasoning in a compare column: its provenance tag, its checks, and its synthesis
    (or an honest decline). A backend error renders calm, never as an alarm."""
    st.markdown(f"<div style='margin-top:4px'>{_prov_reason(entry.model)}</div>", unsafe_allow_html=True)
    if err:
        st.markdown(f"<div class='cs-declined' style='margin-top:6px'>Backend unavailable. {html.escape(err)}</div>",
                    unsafe_allow_html=True)
        return
    _render_checks(reasoning)
    if reasoning.available and reasoning.narrative:
        if reasoning.note:
            st.markdown(f"<div class='cs-sub' style='margin-top:6px'>{chem(reasoning.note, serif=False)}</div>",
                        unsafe_allow_html=True)
        st.markdown(sci(reasoning.narrative.strip()))
    elif reasoning.available:
        note = f" {chem(reasoning.note, serif=False)}" if reasoning.note else ""
        st.markdown(f"<div class='cs-declined' style='margin-top:6px'>No synthesis for this run.{note}</div>",
                    unsafe_allow_html=True)


def render_memo_tab(compound, mol, result) -> None:
    depth = st.session_state.get("depth", "strategy")

    st.markdown("<p class='cs-eyebrow'>Design memo</p>", unsafe_allow_html=True)
    st.markdown(
        "<div class='cs-sub'>Deterministic and provenance-tagged. It renders with no model call. Reasoning is "
        "an optional layer on top, from one model or several: independent viewpoints corroborate, and "
        "disagreement flags where to look.</div>",
        unsafe_allow_html=True,
    )

    entries = state.model_entries()
    ready = [e for e, s in entries if s == "ready"]
    st.markdown("<p class='cs-eyebrow' style='margin-top:12px'>Reasoning models</p>", unsafe_allow_html=True)
    if not ready:
        st.markdown(
            "<div class='cs-declined'>No reasoning model is ready. Set an API key in your .env, or add a local "
            "endpoint under Models in the sidebar.</div>",
            unsafe_allow_html=True,
        )
    else:
        by_label = {e.label: e for e in ready}
        picked = st.multiselect(
            "Reasoning models", list(by_label), default=[ready[0].label], label_visibility="collapsed",
            help="Pick one or several. Agreement corroborates a conclusion; disagreement flags where a single "
                 "model should not be trusted.",
        )
        if st.button("Run reasoning", type="primary", disabled=not picked):
            for label in picked:
                entry = by_label[label]
                k = f"reasoning:{compound.id}:{depth}:{entry.id}"
                st.session_state.pop(k + ":err", None)
                with st.spinner(f"Running {entry.label}"):
                    try:
                        st.session_state[k] = reason_over_design(
                            compound, result, state.reasoning_model_for(entry), depth=depth)
                    except Exception as exc:  # per-model isolation: one model's failure never sinks the others
                        st.session_state[k] = None
                        st.session_state[k + ":err"] = str(exc)

    active = []
    for entry, _s in entries:
        k = f"reasoning:{compound.id}:{depth}:{entry.id}"
        reasoning = st.session_state.get(k)
        err = st.session_state.get(k + ":err")
        if reasoning is not None or err:
            active.append((entry, reasoning, err))
    if active:
        st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
        st.markdown("<p class='cs-eyebrow'>Model reasoning</p>", unsafe_allow_html=True)
        for col, (entry, reasoning, err) in zip(st.columns(len(active)), active):
            with col:
                _model_column(entry, reasoning, err)
        ran = {entry.label: reasoning for entry, reasoning, err in active if reasoning is not None}
        if ran:
            from ..comparison import build_comparison_readme

            st.download_button(
                "Download comparison (README.md)",
                data=build_comparison_readme(compound, mol, result, ran),
                file_name=f"{compound.id}-design-comparison.md", mime="text/markdown",
            )

    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    view = st.segmented_control(
        "Memo view", ["Readable", "Plain text"], default="Readable",
        key=f"memoview_{compound.id}", label_visibility="collapsed",
    ) or "Readable"
    if view == "Readable":
        _memo_body(compound, mol, result, None)
    else:
        st.code(render_memo(compound, mol, result, None), language="text")
