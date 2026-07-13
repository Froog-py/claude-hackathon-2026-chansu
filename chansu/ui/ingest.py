"""Screen: "Add compound" — bring a new compound in from a literature review (Path A).

Three sections: a pure-Python prompt builder, a paste/upload record gate (Producer A), and a
placeholder for model-assisted research-log structuring (Producer B, which arrives with the
multi-model layer). Deterministic: no model runs here. The gate report is styled like the
reasoning-checks panel; declines and unverified citations render calm (`.cs-declined` register),
never as errors. This module arranges and displays only (chansu-design skill).
"""
from __future__ import annotations

import html
import json

import streamlit as st

from ..ingest import derive_vocabulary, validate_record, write_record
from ..ingest_prompts import build_project_setup, build_review_prompt
from . import state

# level -> (label colour, label text). Mirrors the reasoning-checks panel: pass is quiet green,
# a hard fail is the critical red, advisory flags and info are calm/muted (never alarmist).
_LEVEL = {
    "pass": ("var(--pass)", "pass"),
    "fail": ("var(--high)", "fail"),
    "flag": ("var(--ink-2)", "flag"),
    "info": ("var(--ink-3)", "info"),
}
# provenance chip labels for citation checks (the .cs-prov classes carry the colour)
_PROV_LABEL = {"lit": "literature · cited", "uncited": "uncited"}


def _prompt_builder(strategies: list) -> None:
    st.markdown("<p class='cs-eyebrow'>Prompt builder</p>", unsafe_allow_html=True)
    st.markdown(
        "<div class='cs-sub'>Pure Python, no model. Name a compound, copy the prompt into a Claude "
        "Science project, then paste the record it returns below.</div>",
        unsafe_allow_html=True,
    )
    name = st.text_input("Compound name", key="ingest_name", placeholder="e.g. Curcumin")
    focus = st.text_input("Liability focus (optional)", key="ingest_focus", placeholder="e.g. poor_solubility")
    if name:
        st.markdown("<p class='cs-eyebrow' style='margin-top:12px'>Per-compound prompt</p>", unsafe_allow_html=True)
        st.code(build_review_prompt(name, derive_vocabulary(strategies), focus or None), language="text")
    with st.expander("One-time Claude Science project setup (paste once, permanent)"):
        st.code(build_project_setup(), language="text")


def _render_report(report) -> None:
    n_pass = sum(1 for c in report.checks if c.level == "pass")
    head = f"{len(report.checks)} checks. {len(report.fails)} failing, {len(report.flags)} flagged, {n_pass} passed."
    st.markdown(
        f"<p class='cs-eyebrow'>Ingest gate</p><div class='cs-sub'>{html.escape(head)}</div>",
        unsafe_allow_html=True,
    )
    rows = []
    for c in report.checks:
        colour, lbl = _LEVEL.get(c.level, ("var(--ink-3)", c.level))
        link = (f" <a href='{html.escape(c.link)}' target='_blank' style='color:var(--brass)'>source</a>"
                if c.link else "")
        prov = (f" <span class='cs-prov {c.prov}'>{_PROV_LABEL.get(c.prov, c.prov)}</span>" if c.prov else "")
        rows.append(
            "<div style='margin-top:4px;font-size:12px'>"
            f"<span style='font-family:var(--font-mono);font-size:11px;color:{colour}'>{lbl}</span>"
            f"<span style='color:var(--ink-2);margin-left:8px'>{html.escape(c.message)}</span>{prov}{link}</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def _paste_and_gate(strategies: list) -> None:
    st.markdown("<p class='cs-eyebrow'>Paste or upload the record</p>", unsafe_allow_html=True)
    up = st.file_uploader("Record file", type=["json"], key="ingest_file", label_visibility="collapsed")
    raw = st.text_area(
        "Paste the JSON record", key="ingest_raw", height=180, label_visibility="collapsed",
        placeholder="Paste the JSON record returned by Claude Science here",
    )
    if up is not None:
        try:
            text = up.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.markdown(
                "<div class='cs-flagcard'><span class='cs-flag'>invalid</span>File is not valid UTF-8 text; "
                "upload a JSON text file.</div>",
                unsafe_allow_html=True,
            )
            return
    else:
        text = raw
    if not text or not text.strip():
        return
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        st.markdown(
            f"<div class='cs-flagcard'><span class='cs-flag'>invalid</span>Not valid JSON: {html.escape(str(exc))}</div>",
            unsafe_allow_html=True,
        )
        return
    if not isinstance(record, dict):
        st.markdown(
            "<div class='cs-flagcard'><span class='cs-flag'>invalid</span>The record must be a single JSON object.</div>",
            unsafe_allow_html=True,
        )
        return

    existing = set(state.available_compound_ids())
    report = validate_record(record, strategies, existing_ids=existing)
    _render_report(report)

    if not report.ok:
        st.markdown(
            "<div class='cs-sub' style='margin-top:8px'>Fix the failing checks, then re-validate. A record "
            "that cannot become a molecule is not imported.</div>",
            unsafe_allow_html=True,
        )
        return

    ack = True
    if report.flags:
        ack = st.checkbox("I have reviewed the flags above and want to import anyway.", key="ingest_ack")
    if st.button("Import compound", type="primary", disabled=not ack, key="ingest_import"):
        try:
            write_record(report, source="claude-science-import")
        except Exception as exc:  # never crash the tab on a write failure; report it calmly
            st.markdown(
                f"<div class='cs-flagcard'><span class='cs-flag'>error</span>Could not write the record: "
                f"{html.escape(str(exc))}</div>",
                unsafe_allow_html=True,
            )
        else:
            state.available_compound_ids.clear()  # refresh the selector now, not on the 60s TTL
            st.markdown(
                f"<div class='cs-pass'>Imported <b>{html.escape(str(report.compound_id))}</b>. "
                "Select it in the sidebar.</div>",
                unsafe_allow_html=True,
            )


def render_ingest(strategies: list) -> None:
    st.markdown("<p class='cs-eyebrow'>Add compound</p>", unsafe_allow_html=True)
    st.markdown(
        "<div class='cs-sub'>Bring a new compound in from a literature review. Validation is "
        "deterministic and provenance-honest. Adding a compound is data only, never a code change.</div>",
        unsafe_allow_html=True,
    )
    _prompt_builder(strategies)
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    _paste_and_gate(strategies)
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    st.markdown(
        "<p class='cs-eyebrow'>Research-log structuring</p>"
        "<div class='cs-declined'>Model-assisted structuring of an existing research log arrives with the "
        "multi-model layer. Until then, use the prompt builder above with Claude Science.</div>",
        unsafe_allow_html=True,
    )
