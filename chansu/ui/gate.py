"""The two-way-gate live seam (spec: "Two-way gate — live seam"; PROJECT.md non-negotiable #4, §6).

The chemist proposes an edit at a curated site; the tool locates it and runs the *existing* importance
gate live — flag-with-reason if it lands on a high-importance region, pass otherwise — and the chemist can
override with a recorded reason. It surfaces the concern; the human decides.

Sites are data-driven: the compound's modifiable positions (curated attachment handles, §7) *plus* its
importance regions (so you can propose editing an essential region like the warhead and watch it get
flagged). Deduped by the atom they resolve to. Reuses the standalone core functions only
(``resolve_position`` -> ``importance_gate_flags`` -> ``Flag.override``) — no gate logic duplicated, no
compound knowledge added to the engine. This demonstrates the high-importance half of the gate (the
canonical "warhead" moment, §13); the invalid-structure half lives in generation's sanitization.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st

from ..core.generation import importance_gate_flags, resolve_position
from .notation import chem, sci


@dataclass
class _Site:
    key: str
    label: str
    locator: object
    info: str
    atom_idx: object  # int or None


def _edit_sites(compound, mol) -> list:
    """Curated sites a chemist can propose an edit at: modifiable positions first, then any importance
    region not already covered by one (deduped on the resolved atom)."""
    sites: list = []
    seen = set()
    for p in compound.modifiable_positions:
        idx = resolve_position(mol, p.locator)
        sites.append(_Site(f"pos:{p.id}", p.label, p.locator, p.rationale or "", idx))
        if idx is not None:
            seen.add(idx)
    for r in compound.importance_map:
        idx = resolve_position(mol, r.locator)
        if idx is not None and idx in seen:
            continue
        sites.append(_Site(f"imp:{r.id}", r.locator.label or r.id, r.locator, r.reason or "", idx))
        if idx is not None:
            seen.add(idx)
    return sites


def render_gate_seam(compound, mol) -> None:
    sites = _edit_sites(compound, mol)
    if not sites:
        return
    st.markdown("<p class='cs-eyebrow'>Two-way gate</p>", unsafe_allow_html=True)
    st.markdown("### Propose an edit")
    st.caption(
        "The tool never silently blocks *or* allows. Pick a site: if it lands on a high-importance region "
        "it's flagged with the cited reason, and you can override with a recorded reason. It surfaces the "
        "concern; you decide (§6). Sites are the compound's curated handles and essential regions."
    )

    by_label = {sci(s.label): s for s in sites}
    default = sci(sites[0].label)
    chosen = st.segmented_control(
        "Site", list(by_label.keys()), default=default,
        key=f"gate_pos_{compound.id}", label_visibility="collapsed",
    ) or default
    site = by_label[chosen]
    if site.info:
        st.caption(sci(site.info))

    if st.button("Check this edit", key=f"gate_check_{compound.id}"):
        st.session_state[f"gate_checked_{compound.id}"] = site.key
    if st.session_state.get(f"gate_checked_{compound.id}") != site.key:
        return

    flags = importance_gate_flags(compound, mol, site.atom_idx) if site.atom_idx is not None else []
    if not flags:
        st.markdown(
            f"<div class='cs-pass'>No high-importance conflict. An edit at <b>{chem(site.label, serif=False)}</b> "
            "is not in a region the importance map flags. It still needs wet-lab validation like any hypothesis.</div>",
            unsafe_allow_html=True,
        )
        return

    for flag in flags:
        cite = ""
        if getattr(flag, "citation", None) and flag.citation.source:
            cite = ("<div style='margin-top:6px'><span class='cs-prov lit'>literature · cited</span> "
                    f"<span class='cs-cite'>{html.escape(flag.citation.source)}</span></div>")
        st.markdown(
            f"<div class='cs-flagcard'><div><span class='cs-flag'>flag</span>{chem(flag.message, serif=False)}</div>{cite}</div>",
            unsafe_allow_html=True,
        )
        ovr_key = f"gate_ovr_{compound.id}_{site.key}_{flag.region_id}"
        recorded = st.session_state.get(ovr_key)
        if recorded:
            st.markdown(
                f"<div class='cs-sub'>Overridden by chemist. Reason recorded: {html.escape(recorded)}</div>",
                unsafe_allow_html=True,
            )
            continue
        st.markdown(
            "<div class='cs-sub'>Flagged, not forbidden. Override it if the edit is intended.</div>",
            unsafe_allow_html=True,
        )
        reason = st.text_input("Override reason (recorded)", key=f"reason_{ovr_key}")
        if st.button("Record override", key=f"btn_{ovr_key}"):
            try:
                flag.override(reason)                         # the real §6 mechanism (rejects an empty reason)
                st.session_state[ovr_key] = flag.override_reason
                st.rerun()
            except ValueError as exc:
                st.markdown(
                    f"<div class='cs-sub' style='color:var(--high)'>{html.escape(str(exc))}</div>",
                    unsafe_allow_html=True,
                )
