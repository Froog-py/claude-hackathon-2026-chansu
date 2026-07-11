"""Deterministic property module (PROJECT.md §6 — the RDKit side of the trust boundary).

Math, not opinion. Every value here is ``Provenance.COMPUTED``. No prediction of binding,
toxicity, or efficacy lives in this file or anywhere else (PROJECT.md §6, §14).
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass

from rdkit.Chem import (
    DataStructs,
    Descriptors,
    Mol,
    RDConfig,
    rdFingerprintGenerator,
    rdMolDescriptors,
)

# Synthetic-accessibility scorer ships in RDKit's Contrib tree, not the main namespace.
# Import it lazily and guardedly so a missing Contrib dir fails loudly rather than silently.
_sascorer = None


def _sa_scorer():
    global _sascorer
    if _sascorer is None:
        sa_path = os.path.join(RDConfig.RDContribDir, "SA_Score")
        if not os.path.isdir(sa_path):
            raise RuntimeError(
                f"RDKit SA_Score Contrib module not found at {sa_path}. "
                "Synthetic-accessibility scoring is unavailable in this install."
            )
        if sa_path not in sys.path:
            sys.path.append(sa_path)
        import sascorer  # type: ignore

        _sascorer = sascorer
    return _sascorer


_MORGAN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)  # ECFP4-like


@dataclass
class PropertyProfile:
    """All Day-1 deterministic descriptors. Every field is [computed]."""

    formula: str
    mw: float
    logp: float                 # Crippen clogP (RDKit MolLogP)
    tpsa: float
    hbd: int
    hba: int
    rotatable_bonds: int
    sa_score: float             # 1 (easy) .. 10 (hard)
    lipinski_violations: int    # count of Ro5 criteria breached (0..4)
    lipinski_pass: bool         # Rule of Five allows <= 1 violation
    veber_pass: bool            # rotatable bonds <= 10 and TPSA <= 140

    def as_dict(self) -> dict:
        return asdict(self)


def compute_properties(mol: Mol) -> PropertyProfile:
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    rotb = rdMolDescriptors.CalcNumRotatableBonds(mol)
    sa = _sa_scorer().calculateScore(mol)

    violations = int(mw > 500) + int(logp > 5) + int(hbd > 5) + int(hba > 10)
    veber = rotb <= 10 and tpsa <= 140

    return PropertyProfile(
        formula=rdMolDescriptors.CalcMolFormula(mol),
        mw=round(mw, 3),
        logp=round(logp, 3),
        tpsa=round(tpsa, 3),
        hbd=hbd,
        hba=hba,
        rotatable_bonds=rotb,
        sa_score=round(sa, 3),
        lipinski_violations=violations,
        lipinski_pass=violations <= 1,
        veber_pass=veber,
    )


def tanimoto_similarity(a: Mol, b: Mol) -> float:
    """Tanimoto similarity of Morgan (ECFP4-like) fingerprints. Used for similarity-to-parent."""
    fa = _MORGAN.GetFingerprint(a)
    fb = _MORGAN.GetFingerprint(b)
    return DataStructs.TanimotoSimilarity(fa, fb)
