"""Molecule-rendering helpers: substructure atom resolution, 2D SVG, and 3D coordinates (PROJECT.md §11).

These are the framework-agnostic pieces the Streamlit viewer composes — so they are tested here without any
Streamlit, proving the chemistry stays out of the UI. They are pure RDKit and deterministic.
"""

from rdkit import Chem
from rdkit.Chem import AllChem

from chansu.core.generation import region_match_atoms, resolve_position
from chansu.core.loaders import load_compound, to_mol
from chansu.core.models import StructureLocator
from chansu.render_mol import draw_molecule_svg, molblock_3d


def _bufalin():
    c = load_compound("bufalin")
    return c, to_mol(c)


# --- region_match_atoms ----------------------------------------------------------------------

def test_region_match_atoms_covers_the_region_and_contains_the_anchor():
    """The highlighted atom set is the whole first SMARTS match and always contains the anchor atom
    resolve_position picks — so highlighting stays consistent with the gate/position logic."""
    compound, mol = _bufalin()
    assert compound.importance_map, "fixture expects a curated importance map"
    for region in compound.importance_map:
        atoms = region_match_atoms(mol, region.locator)
        anchor = resolve_position(mol, region.locator)
        assert atoms, f"region {region.id} should resolve to at least one atom"
        assert anchor in atoms  # the anchor is part of the highlighted region
        assert len(atoms) == len(set(atoms))  # no duplicate indices


def test_region_match_atoms_empty_when_no_match():
    """A non-matching (but valid) SMARTS yields [] — a region that can't be located is simply not
    highlighted, never an error."""
    _, mol = _bufalin()
    # phosphorus does not appear in bufalin
    assert region_match_atoms(mol, StructureLocator(smarts="[P]", target_atom=0)) == []


# --- draw_molecule_svg -----------------------------------------------------------------------

def test_draw_molecule_svg_returns_svg_and_is_deterministic():
    _, mol = _bufalin()
    svg = draw_molecule_svg(mol)
    assert "<svg" in svg
    assert draw_molecule_svg(mol) == svg  # same input -> identical output


def test_draw_molecule_svg_highlight_changes_output_without_mutating_input():
    compound, mol = _bufalin()
    before_atoms = mol.GetNumAtoms()
    before_confs = mol.GetNumConformers()             # 0 for a fresh MolFromSmiles
    region = compound.importance_map[0]
    highlight = {a: (0.85, 0.15, 0.24) for a in region_match_atoms(mol, region.locator)}
    plain = draw_molecule_svg(mol)
    highlighted = draw_molecule_svg(mol, highlight_atoms=highlight)
    assert "<svg" in highlighted
    assert highlighted != plain                       # the overlay is actually drawn
    assert mol.GetNumAtoms() == before_atoms
    # the real no-mutation invariant: drawing must NOT add a 2D conformer to the caller's mol (which
    # would corrupt a later 3D embed of the same mol) — guarded only by the internal Chem.Mol(mol) copy.
    assert mol.GetNumConformers() == before_confs


# --- molblock_3d -----------------------------------------------------------------------------

def test_molblock_3d_has_real_3d_coordinates():
    _, mol = _bufalin()
    block = molblock_3d(mol)
    assert block is not None and "V2000" in block
    embedded = Chem.MolFromMolBlock(block, removeHs=False)
    assert embedded is not None and embedded.GetNumConformers() == 1
    conf = embedded.GetConformer()
    zs = [abs(conf.GetAtomPosition(i).z) for i in range(embedded.GetNumAtoms())]
    assert max(zs) > 1e-6  # genuinely 3D, not a flattened depiction


def test_molblock_3d_preserves_heavy_atom_indices():
    """AddHs appends hydrogens after the heavy atoms, so a heavy-atom index on the no-H mol still refers
    to the same atom in the embedded (with-H) structure — the invariant 3D highlighting relies on."""
    _, mol = _bufalin()
    block = molblock_3d(mol)
    embedded = Chem.MolFromMolBlock(block, removeHs=False)
    for i in range(mol.GetNumAtoms()):
        assert embedded.GetAtomWithIdx(i).GetSymbol() == mol.GetAtomWithIdx(i).GetSymbol()
