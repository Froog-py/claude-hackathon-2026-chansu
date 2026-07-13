"""Workspace screen (spec: "Screen 1 — Workspace"): identity, computed properties, the molecule viewer,
the two-way-gate live seam, and cited grounding.

Arranges and displays only — the molecule viewer and gate seam compose the framework-agnostic render
helpers and standalone gate functions; the computed profile comes straight from the RDKit property engine
(``[computed]`` — the deterministic half of the trust boundary, §6).
"""

from __future__ import annotations

import html

import streamlit as st

from ..core.properties import compute_properties
from .notation import chem, formula


def _esc(x) -> str:
    return html.escape(str(x))


def _hero(compound) -> None:
    class_ = compound.annotations.get("class")
    chip = f"<span class='cs-chip'>{_esc(class_)}</span>" if class_ else ""
    extra = [a for a in compound.aliases if a.strip().lower() != compound.name.strip().lower()]
    sub = f"<p class='cs-sub'>Also known as {chem(', '.join(extra), serif=True)}</p>" if extra else ""
    st.markdown(
        f"<p class='cs-eyebrow'>Compound</p>"
        f"<div style='display:flex;align-items:baseline;gap:14px;flex-wrap:wrap'>"
        f"<span class='cs-name'>{_esc(compound.name)}</span>{chip}</div>{sub}",
        unsafe_allow_html=True,
    )
    src = " ".join(p for p in (compound.source, compound.source_id) if p) or "unsourced"
    st.markdown(
        "<div class='cs-kv'>"
        f"<span><span class='k'>Source</span><br><span class='v'>{_esc(src)}</span></span>"
        f"<span><span class='k'>Compound id</span><br><span class='v'>{_esc(compound.id)}</span></span>"
        "</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Canonical SMILES (machine-readable)"):
        st.code(compound.smiles, language="text")


def _properties(mol) -> None:
    p = compute_properties(mol)
    lip_cls = "ok" if p.lipinski_pass else "warn"
    veb_cls = "ok" if p.veber_pass else "warn"
    cells = [
        (f"{p.mw:.1f}", "MW g/mol"),
        (f"{p.logp:.2f}", "clogP"),
        (f"{p.tpsa:.1f}", "TPSA Å²"),
        (p.hbd, "H-bond donors"),
        (p.hba, "H-bond acc."),
        (p.rotatable_bonds, "Rot. bonds"),
        (f"{p.sa_score:.1f}", "Synth. access"),
    ]
    formula_stat = f"<div class='cs-stat'><div class='n'>{formula(p.formula)}</div><div class='l'>Formula</div></div>"
    stat_html = "".join(f"<div class='cs-stat'><div class='n'>{_esc(v)}</div><div class='l'>{_esc(l)}</div></div>" for v, l in cells)
    lip = f"<div class='cs-stat'><div class='n {lip_cls}'>{'pass' if p.lipinski_pass else 'fail'}</div><div class='l'>Lipinski Ro5 · {p.lipinski_violations} viol.</div></div>"
    veb = f"<div class='cs-stat'><div class='n {veb_cls}'>{'pass' if p.veber_pass else 'fail'}</div><div class='l'>Veber</div></div>"
    st.markdown("<p class='cs-eyebrow'>Computed properties · RDKit</p>", unsafe_allow_html=True)
    st.markdown(f"<div class='cs-stats'>{formula_stat}{stat_html}{lip}{veb}</div>", unsafe_allow_html=True)
    st.caption("Deterministic. Math, not opinion. Every value is `[computed]` and reproducible from the verified structure.")


def _cite(obj) -> str:
    c = getattr(obj, "citation", None)
    if c is not None and c.source:
        return (
            "<span class='cs-prov lit'>literature · cited</span> "
            f"<span class='cs-cite'>{_esc(c.source)}</span>"
        )
    return "<span class='cs-prov uncited'>uncited</span>"


def _grounding(compound) -> None:
    st.markdown("<p class='cs-eyebrow'>Grounding · cited</p>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown("###### Targets")
        for t in compound.targets:
            st.markdown(
                f"<div class='cs-card'><div class='t'>{chem(t.name)}</div>"
                f"<div class='d'>{chem(t.role or '', serif=False)}</div>{_cite(t)}</div>",
                unsafe_allow_html=True,
            )
    with right:
        st.markdown("###### Liabilities")
        for lib in compound.liabilities:
            kind = _esc(lib.kind.replace("_", " ").capitalize())
            st.markdown(
                f"<div class='cs-card'><div class='t'>{kind}</div>"
                f"<div class='d'>{chem(lib.detail or '', serif=False)}</div>{_cite(lib)}</div>",
                unsafe_allow_html=True,
            )

    st.markdown("###### Importance map · graded, advisory")
    for r in compound.importance_map:
        lvl = r.importance.lower()
        st.markdown(
            f"<div class='cs-card'><div class='t'><span class='cs-imp {lvl}'>{_esc(r.importance.upper())}</span>{chem(r.locator.label or r.id)}</div>"
            f"<div class='d'>{chem(r.reason, serif=False)}</div>{_cite(r)}</div>",
            unsafe_allow_html=True,
        )


def render_workspace(compound, mol, result) -> None:
    from .gate import render_gate_seam
    from .viewer import render_viewer

    _hero(compound)
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    render_viewer(compound, mol)
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    _properties(mol)
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    render_gate_seam(compound, mol)
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    _grounding(compound)
