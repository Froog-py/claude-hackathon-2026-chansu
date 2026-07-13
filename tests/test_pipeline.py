"""Day-4 tests: the full loop — generate across strategies, gate, score, memo (BUILD_PLAN.md).

The must-ship, made executable: feeding bufalin yields valid ranked candidates whose scores are
transparent, whose high-importance edits are flagged (not blocked), and whose memo declines to
over-claim where nothing applies.
"""

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from chansu.core.loaders import load_compound, load_strategies, to_mol
from chansu.core.pipeline import design, ranked_valid
from chansu.core.scoring import DEFAULT_WEIGHTS, score
from chansu.report import design_and_render, render_memo


def test_design_loop_generates_gates_and_scores():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())

    valid = ranked_valid(result)
    assert valid, "no valid candidate generated"
    # ranked by score, descending
    assert all(valid[i].score.total >= valid[i + 1].score.total for i in range(len(valid) - 1))

    # the soft-drug strategy generates at both hydroxyl handles; exactly the C14 edit trips the
    # two-way gate (essential C14-OH), the C3 edit does not.
    soft = [c for c in valid if c.strategy.id == "soft_drug_self_inactivation"]
    assert len(soft) == 2
    flagged = [c for c in soft if any(f.code == "high_importance_region" for f in c.flags)]
    unflagged = [c for c in soft if not c.flags]
    assert len(flagged) == 1 and len(unflagged) == 1  # gate fires on exactly one

    # every valid candidate is a re-parseable structure with a computed property profile
    for c in valid:
        assert Chem.MolFromSmiles(c.analog.product_smiles) is not None
        assert c.properties and c.properties["formula"]

    # honest failure: rapid_clearance has no precedented strategy
    assert any(lib.kind == "rapid_clearance" for lib in result.unaddressed)


def test_score_is_transparent_and_bounded():
    mol = to_mol(load_compound("bufalin"))
    analog = Chem.MolFromSmiles("CC(=O)O[C@H]1CC[C@@]2(C)[C@H](CC[C@@H]3[C@@H]2CC[C@]2(C)[C@@H](c4ccc(=O)oc4)CC[C@]32O)C1")
    s = score(mol, analog)
    for component in (s.similarity, s.ease, s.druglikeness, s.total):
        assert 0.0 <= component <= 1.0
    # The equation the memo prints (rounded components) must reproduce the stored total *exactly*
    # at the shown precision — not merely within a loose tolerance (Codex P2).
    expected = round(
        s.weights["similarity"] * s.similarity
        + s.weights["ease"] * s.ease
        + s.weights["druglikeness"] * s.druglikeness,
        3,
    )
    assert s.total == expected
    assert s.weights == DEFAULT_WEIGHTS


def test_score_rejects_invalid_weights():
    """Custom weights are validated so ``total`` cannot silently leave [0, 1] (Codex P2)."""
    mol = to_mol(load_compound("bufalin"))
    analog = Chem.MolFromSmiles("CCO")
    for bad in (
        {"similarity": 1.0, "ease": 1.0, "druglikeness": 1.0},   # sum != 1
        {"similarity": 0.5, "ease": 0.5},                        # missing key
        {"similarity": -0.5, "ease": 0.75, "druglikeness": 0.75},  # negative
        {"similarity": float("nan"), "ease": 0.5, "druglikeness": 0.5},  # non-finite
        {"similarity": 0.5, "ease": 0.25, "druglikeness": 0.25, "extra": 0.0},  # unknown key
    ):
        with pytest.raises(ValueError):
            score(mol, analog, weights=bad)


def test_memo_is_the_tagged_must_ship_deliverable():
    compound = load_compound("bufalin")
    memo = design_and_render(compound, to_mol(compound), load_strategies())

    assert "DESIGN MEMO" in memo
    assert "score =" in memo and "similarity-to-parent" in memo  # transparent rubric shown
    assert "[hypothesis · needs wet-lab validation]" in memo      # candidates tagged as hypotheses
    assert "[literature · cited]" in memo and "PMID 20388710" in memo  # cited grounding
    assert "FLAG [warning]" in memo and "high-importance" in memo.lower()  # two-way gate visible
    assert "overridable" in memo                                   # gate allows override
    assert "no strategy in the current curated library" in memo    # bounded honest failure
    assert "formulation-delivery" not in memo                      # invents no out-of-scope route
    assert "predicts binding, toxicity, or efficacy" in memo       # non-goals restated


def test_gate_override_survives_into_the_memo():
    """The other half of the two-way gate: a chemist overrides a flag on the design result, and
    that reason is rendered in the memo — orchestration and rendering are separate (Codex P1)."""
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())

    # the high-importance C14 acetylation candidate carries the gate flag
    flagged = [
        c for c in result.candidates
        if c.analog.valid and any(f.code == "high_importance_region" for f in c.flags)
    ]
    assert flagged, "expected a high-importance gate flag to override"
    flag = next(f for f in flagged[0].flags if f.code == "high_importance_region")
    flag.override("intended tuning of the warhead — chemist accepts the risk")

    memo = render_memo(compound, mol, result)
    assert "OVERRIDDEN by chemist" in memo
    assert "intended tuning of the warhead" in memo
    # a fresh (un-reviewed) render of the same compound shows no override — proving it came from
    # the reviewed result, not from re-running design
    assert "OVERRIDDEN by chemist" not in design_and_render(compound, mol, load_strategies())


def test_described_candidates_are_per_position_gated_and_rendered():
    """A strategy with no encoded transformation but two actionable positions yields one described
    candidate PER position (not one collapsed positionless one), the described edit at the essential
    C14 site carries the high-importance gate flag, and the memo renders position + description +
    flags for described candidates (Codex P1)."""
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())

    # glycosylation has no transformation; bufalin exposes two hydroxyl handles -> two candidates
    glyco = [c for c in result.candidates if c.strategy.id == "glycosylation_isoform_selectivity"]
    assert {c.position_id for c in glyco} == {"c3_oh", "c14_oh"}
    assert all(c.analog.describe_only for c in glyco)

    c14 = next(c for c in glyco if c.position_id == "c14_oh")
    c3 = next(c for c in glyco if c.position_id == "c3_oh")
    assert any(f.code == "high_importance_region" for f in c14.flags)  # essential site -> gated
    assert not any(f.code == "high_importance_region" for f in c3.flags)  # C3 is not high-importance

    memo = render_memo(compound, mol, result)
    assert "[describe] glycosylation_isoform_selectivity at C14 tertiary hydroxyl" in memo
