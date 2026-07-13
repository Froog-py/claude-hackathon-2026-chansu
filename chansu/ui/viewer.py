"""The molecule viewer (spec: "The molecule viewer") — MolView-style skeletal + multi-representation 3D.

Two rendering engines composed from the framework-agnostic render helpers: a 2D skeletal structure (RDKit
SVG) and an interactive 3D viewer (py3Dmol / 3Dmol.js) — ball & stick, stick, spheres, wireframe. Both
render on a dark ground to match the app theme. Element colouring is always on; the importance-map overlay
is an independent toggle. This module holds NO chemistry — it calls ``region_match_atoms`` /
``draw_molecule_svg`` / ``molblock_3d`` and maps importance levels to colours.

Importance-overlay colours use the design system's importance ramp (high red, medium amber, low slate;
chansu-design section 2), so the molecule overlay matches the importance pills shown elsewhere in the
app. The ramp is muted and desaturated, which keeps it distinguishable from the saturated CPK element
palette (O red, N blue, C grey) it sits over.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from ..core.generation import region_match_atoms
from ..render_mol import draw_molecule_svg, molblock_3d

# Importance -> overlay colour: the design system's importance ramp (chansu-design section 2), so the
# molecule overlay matches the importance pills. Muted/desaturated, distinguishable from saturated CPK.
_RGB = {"high": (0.851, 0.439, 0.439), "medium": (0.831, 0.635, 0.290), "low": (0.431, 0.588, 0.706)}
_HEX = {"high": "#D97070", "medium": "#D4A24A", "low": "#6E96B4"}

_SKELETAL = "Skeletal"
_STYLE_3D = {
    "Ball & stick": ("stick", {"stick": {"radius": 0.13}, "sphere": {"scale": 0.28}}),
    "Stick": ("stick", {"stick": {}}),
    "Spheres": ("sphere", {"sphere": {}}),
    "Wireframe": ("line", {"line": {}}),
}
_REPRESENTATIONS = [_SKELETAL, *_STYLE_3D.keys()]

_W, _H = 880, 500
_BG_3D = "#0E1216"


def _highlights_2d(compound, mol) -> dict:
    out: dict = {}
    for region in compound.importance_map:
        color = _RGB.get(region.importance)
        if color is None:
            continue
        for atom in region_match_atoms(mol, region.locator):
            out[atom] = color
    return out


def _atoms_by_level(compound, mol) -> dict:
    out: dict = {}
    for region in compound.importance_map:
        bucket = out.setdefault(region.importance, [])
        for atom in region_match_atoms(mol, region.locator):
            if atom not in bucket:
                bucket.append(atom)
    return out


def _legend(compound) -> None:
    present = [lvl for lvl in ("high", "medium", "low") if any(r.importance == lvl for r in compound.importance_map)]
    if not present:
        return
    items = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:7px;margin-right:20px'>"
        f"<span style='width:11px;height:11px;border-radius:3px;background:{_HEX[l]};display:inline-block'></span>"
        f"<span style='font-family:var(--font-mono);font-size:11px;letter-spacing:0.04em;color:var(--ink-2)'>{l.title()} importance</span></span>"
        for l in present
    )
    st.markdown(f"<div style='margin-top:8px'>{items}</div>", unsafe_allow_html=True)


def _render_2d(compound, mol, highlight_on: bool) -> None:
    highlights = _highlights_2d(compound, mol) if highlight_on else None
    svg = draw_molecule_svg(mol, highlight_atoms=highlights, size=(_W, _H), dark=True)
    components.html(f"<div style='display:flex;justify-content:center'>{svg}</div>", height=_H + 16)


def _render_3d(compound, mol, style, highlight_on: bool) -> None:
    block = molblock_3d(mol)
    if block is None:
        st.warning("3D coordinates could not be generated for this structure. Showing the skeletal view instead.")
        _render_2d(compound, mol, highlight_on)
        return
    try:
        import py3Dmol
    except ImportError:
        _render_2d(compound, mol, highlight_on)
        return

    _base_key, style_dict = style
    view = py3Dmol.view(width=_W, height=_H)
    view.setBackgroundColor(_BG_3D)
    view.addModel(block, "mol")
    view.setStyle(style_dict)
    if highlight_on:
        for level, atoms in _atoms_by_level(compound, mol).items():
            hexc = _HEX.get(level)
            if hexc and atoms:
                # a translucent shell in the ramp colour over the element style: element identity stays
                # underneath, so a same-hue element colour never clashes (chansu-design section 2)
                view.addStyle({"index": atoms}, {"sphere": {"color": hexc, "opacity": 0.5}})
    view.zoomTo()
    components.html(view._make_html(), height=_H + 16)
    st.caption("Drag to rotate · scroll to zoom · right-drag to pan. Loads the 3Dmol.js viewer from a CDN.")


def render_viewer(compound, mol) -> None:
    st.markdown("<p class='cs-eyebrow'>Structure · rdkit + 3dmol</p>", unsafe_allow_html=True)
    controls = st.columns([3, 1])
    with controls[0]:
        choice = st.segmented_control(
            "Representation", _REPRESENTATIONS, default=_SKELETAL,
            key=f"repr_{compound.id}", label_visibility="collapsed",
        ) or _SKELETAL
    with controls[1]:
        highlight_on = st.toggle(
            "Highlight importance", value=True, key=f"hl_{compound.id}",
            help="Overlay the graded importance regions. Element colouring (O red, N blue, …) stays on either way.",
        )
    if choice == _SKELETAL:
        _render_2d(compound, mol, highlight_on)
    else:
        _render_3d(compound, mol, _STYLE_3D[choice], highlight_on)
    if highlight_on:
        _legend(compound)
