"""Load data (compounds, transformations) into the generic model and build RDKit mols.

This is the only place the engine reads compound/transformation *data*. Adding a compound
or a transformation is a new JSON file under ``data/`` — never a code change (PROJECT.md §5).
SMILES are validated and canonicalized here so the rest of the core can trust them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rdkit import Chem
from rdkit.Chem import Mol

from .models import (
    Citation,
    Compound,
    ImportanceRegion,
    Liability,
    ModifiablePosition,
    StructureLocator,
    Target,
    Transformation,
)

# Repo layout: chansu/core/loaders.py -> parents[2] == repo root -> data/
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def data_dir(override: Optional[Path] = None) -> Path:
    return Path(override) if override else DEFAULT_DATA_DIR


def to_mol(compound: Compound) -> Mol:
    """RDKit mol for a loaded compound. Raises if the SMILES is invalid (should not
    happen — it was validated at load — but the core never trusts silently)."""
    mol = Chem.MolFromSmiles(compound.smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES for compound {compound.id!r}: {compound.smiles!r}")
    return mol


def _citation(d: Optional[dict]) -> Optional[Citation]:
    if not d:
        return None
    return Citation(label=d.get("label", ""), source=d.get("source"), note=d.get("note"))


def _locator(d: dict) -> StructureLocator:
    return StructureLocator(
        smarts=d["smarts"], target_atom=d.get("target_atom", 0), label=d.get("label")
    )


def compound_from_dict(d: dict) -> Compound:
    smiles = d["structure"]["smiles"]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES in data for compound {d.get('id')!r}: {smiles!r}")
    canonical = Chem.MolToSmiles(mol)  # keeps stereochemistry

    positions = [
        ModifiablePosition(
            id=p["id"],
            label=p["label"],
            locator=_locator(p["locator"]),
            attachment_types=p.get("attachment_types", []),
            rationale=p.get("rationale"),
        )
        for p in d.get("modifiable_positions", [])
    ]
    importance = [
        ImportanceRegion(
            id=r["id"],
            locator=_locator(r["locator"]),
            importance=r["importance"],
            reason=r["reason"],
            citation=_citation(r.get("citation")),
        )
        for r in d.get("importance_map", [])
    ]
    targets = [
        Target(name=t["name"], role=t.get("role"), citation=_citation(t.get("citation")))
        for t in d.get("targets", [])
    ]
    liabilities = [
        Liability(kind=l["kind"], detail=l.get("detail"), citation=_citation(l.get("citation")))
        for l in d.get("liabilities", [])
    ]
    return Compound(
        id=d["id"],
        name=d["name"],
        smiles=canonical,
        source=d["structure"].get("source"),
        source_id=d["structure"].get("source_id"),
        inchikey=d["structure"].get("inchikey"),
        aliases=d.get("aliases", []),
        annotations=d.get("annotations", {}),
        modifiable_positions=positions,
        importance_map=importance,
        targets=targets,
        liabilities=liabilities,
    )


def transformation_from_dict(d: dict) -> Transformation:
    return Transformation(
        id=d["id"],
        name=d["name"],
        reaction_smarts=d["reaction_smarts"],
        reacting_atom_mapnum=d["reacting_atom_mapnum"],
        applies_to_attachment_types=d.get("applies_to_attachment_types", []),
        description=d.get("description", ""),
    )


def load_compound(compound_id: str, override: Optional[Path] = None) -> Compound:
    path = data_dir(override) / "compounds" / f"{compound_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No compound data file: {path}")
    return compound_from_dict(json.loads(path.read_text()))


def load_transformation(transformation_id: str, override: Optional[Path] = None) -> Transformation:
    path = data_dir(override) / "transformations" / f"{transformation_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No transformation data file: {path}")
    return transformation_from_dict(json.loads(path.read_text()))


def load_config(override: Optional[Path] = None) -> dict:
    """App-level config (e.g. which compound the demo entry point loads). Kept in data so
    the engine/CLI carry no compound-specific default."""
    path = data_dir(override) / "config.json"
    return json.loads(path.read_text()) if path.exists() else {}
