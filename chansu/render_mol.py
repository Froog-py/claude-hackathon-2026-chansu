"""Molecule rendering helpers (PROJECT.md §11) — a framework-agnostic sibling to ``report.py``.

``report.py`` renders the design as text; this renders the *structure*: a 2D Lewis-structure SVG (via
RDKit's 2D drawer) and 3D coordinates as an MDL molblock (for a 3D viewer to consume). Both are pure,
deterministic RDKit — **no Streamlit, no viewer library** here, so the interface layer can compose these
without any chemistry leaking into UI code, and they are unit-testable without a browser.

The picture is drawn from the *verified* structure (this is the ChemDraw-like feature, §11): it is the
actual molecule, reproducible, not a scraped image.
"""

from __future__ import annotations

from typing import Optional

from rdkit import Chem
from rdkit.Chem import AllChem, Mol, rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

# RGB colour, each channel in 0..1 (RDKit's highlight colour convention).
Color = tuple


def draw_molecule_svg(
    mol: Mol,
    highlight_atoms: Optional[dict] = None,   # {atom_idx: (r, g, b)} in 0..1
    size: tuple = (520, 400),
    dark: bool = False,
) -> str:
    """A 2D Lewis-structure SVG. Element colouring is always on (RDKit default); ``highlight_atoms`` adds
    the importance-map overlay as coloured halos over the mapped atoms (and the bonds internal to a
    highlighted set), leaving the element colouring intact. Deterministic for a given input.

    Operates on a copy so the caller's ``mol`` is never mutated (a 2D conformer is added for drawing).
    """
    m = Chem.Mol(mol)
    if m.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(m)

    atoms: list = []
    atom_colors: dict = {}
    bonds: list = []
    bond_colors: dict = {}
    if highlight_atoms:
        atoms = list(highlight_atoms.keys())
        atom_colors = dict(highlight_atoms)
        hset = set(highlight_atoms)
        for bond in m.GetBonds():
            a1, a2 = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            if a1 in hset and a2 in hset:
                bonds.append(bond.GetIdx())
                bond_colors[bond.GetIdx()] = highlight_atoms[a1]

    drawer = rdMolDraw2D.MolDraw2DSVG(size[0], size[1])
    if dark:
        rdMolDraw2D.SetDarkMode(drawer)  # dark background + light bonds/atoms, to match a dark UI theme
    rdMolDraw2D.PrepareAndDrawMolecule(
        drawer, m,
        highlightAtoms=atoms, highlightAtomColors=atom_colors,
        highlightBonds=bonds, highlightBondColors=bond_colors,
    )
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def molblock_3d(mol: Mol) -> Optional[str]:
    """3D MDL molblock for a 3D viewer: ``AddHs -> EmbedMolecule (ETKDG) -> MMFFOptimizeMolecule
    (best-effort) -> MolToMolBlock``. ``AddHs`` appends hydrogens *after* the heavy atoms, so heavy-atom
    indices are preserved — importance atom indices computed on the no-H mol stay valid for 3D highlighting.

    Returns ``None`` on embedding failure (the viewer falls back to 2D) rather than raising — a structure
    that cannot be embedded is an honest "no 3D", not a crash. Deterministic (fixed embed seed).
    """
    m = Chem.AddHs(Chem.Mol(mol))
    params = AllChem.ETKDGv3()
    params.randomSeed = 42  # reproducible coordinates across runs
    if AllChem.EmbedMolecule(m, params) != 0:
        return None
    try:
        AllChem.MMFFOptimizeMolecule(m)
    except Exception:
        pass  # best-effort refinement; the embedded coordinates are already valid
    return Chem.MolToMolBlock(m)
