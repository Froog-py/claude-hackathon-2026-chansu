"""Tests for the comparison README builder (each model's section + honest declines, no fabrication)."""
from chansu.comparison import build_comparison_readme
from chansu.core.loaders import load_compound, load_strategies, to_mol
from chansu.core.pipeline import design
from chansu.reasoning.design_reasoning import DesignReasoning


def _fixture():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())
    return compound, mol, result


def test_readme_includes_each_model_and_declines():
    compound, mol, result = _fixture()
    reasonings = {
        "Claude": DesignReasoning(model_name="claude", available=True, narrative="A synthesis paragraph."),
        "Local": DesignReasoning(model_name="local", available=False, note="backend unavailable"),
    }
    md = build_comparison_readme(compound, mol, result, reasonings)
    assert "# Chansu design memo" in md
    assert "### Claude" in md and "A synthesis paragraph." in md
    assert "### Local" in md and "No reasoning" in md  # decline shown, not hidden
