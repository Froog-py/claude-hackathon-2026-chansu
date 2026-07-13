"""Sources / Reference screen (spec: "Screen 3 — Sources", read + auto-organize).

Organizes the citations that already exist in the data (built by ``references.build_reference_index``)
into a Zotero-style, groupable list — no new authoring, nothing fabricated. Grouping/sorting is pure
presentation over the ``Reference`` list.
"""

from __future__ import annotations

import html

import streamlit as st

from ..references import build_reference_index
from .notation import sci

_META = "font-family:var(--font-mono);font-size:11px;letter-spacing:0.02em;color:var(--ink-3)"

_GROUP_BY = {
    "Subject": "subjects",
    "Role": "roles",
    "Source type": None,   # derived below (PubMed / DOI / URL / other)
    "Flat list": "flat",
}


def _source_type(ref) -> str:
    if ref.pmid:
        return "PubMed (PMID)"
    if ref.doi:
        return "DOI"
    if ref.urls:
        return "URL"
    return "Uncited link"


def _grouped(refs, group_by: str) -> dict:
    """Map group-label -> list[Reference]. A paper backing several subjects/roles appears under each
    (Zotero-like, correct)."""
    field = _GROUP_BY[group_by]
    groups: dict = {}
    for ref in refs:
        if field == "flat":
            keys = ["All references"]
        elif field is None:  # source type
            keys = [_source_type(ref)]
        else:
            keys = getattr(ref, field) or ["(unclassified)"]
        for k in keys:
            groups.setdefault(k, []).append(ref)
    return groups


def _render_card(ref) -> None:
    st.markdown(f"**{sci(ref.citation)}**")
    chips = " · ".join(f"`{r}`" for r in ref.roles)
    links = " · ".join(f"[{('PubMed' if 'pubmed' in u else 'DOI' if 'doi.org' in u else 'link')}]({u})" for u in ref.urls)
    meta = " ".join(x for x in (chips, links) if x)
    if meta:
        st.markdown(meta)
    with st.expander(f"Details · backs {len(ref.backs)} claim(s)"):
        for role, subject in ref.backs:
            st.markdown(f"- `{role}` → {sci(subject)}")
        if ref.pmid:
            st.markdown(f"<span style='{_META}'>PMID {html.escape(str(ref.pmid))}</span>", unsafe_allow_html=True)
        if ref.doi:
            st.markdown(f"<span style='{_META}'>DOI {html.escape(str(ref.doi))}</span>", unsafe_allow_html=True)
        for note in ref.notes:
            st.caption(note)


def render_sources(compound, strategies) -> None:
    refs = build_reference_index(compound, strategies)
    st.subheader("Sources & references")
    st.caption(
        f"{len(refs)} papers, aggregated from every cited claim on this compound and the strategy "
        "library. Nothing here is fabricated. Each entry is a real citation already in the data (§6, §9)."
    )

    controls = st.columns(2)
    with controls[0]:
        group_by = st.selectbox("Group by", list(_GROUP_BY.keys()), index=0)
    with controls[1]:
        sort_by = st.selectbox("Sort by", ["Claims backed (most first)", "Citation name"], index=0)

    def _sort(items):
        if sort_by.startswith("Claims"):
            return sorted(items, key=lambda r: (-len(r.backs), r.citation.lower()))
        return sorted(items, key=lambda r: r.citation.lower())

    groups = _grouped(refs, group_by)
    for label in sorted(groups.keys()):
        items = _sort(groups[label])
        st.markdown(f"### {label}  ·  {len(items)}")
        for ref in items:
            with st.container(border=True):
                _render_card(ref)
