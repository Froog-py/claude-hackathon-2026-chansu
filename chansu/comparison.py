"""Assemble a downloadable README comparing each model's reasoning over the same deterministic design.
Pure text; reuses ``report.render_memo`` and invents no claim. Declines are shown as declines (§6).
Reusable by the UI and a future MCP surface.
"""
from __future__ import annotations

from .report import render_memo


def build_comparison_readme(compound, mol, result, reasonings: dict) -> str:
    """``reasonings``: ``{model_label: DesignReasoning | None}``. Renders the deterministic memo once
    (model-agnostic), then each model's reasoning section (or its honest decline)."""
    out = [
        f"# Chansu design memo — {compound.name}",
        "",
        render_memo(compound, mol, result, None),
        "",
        "## Model reasoning (comparison)",
    ]
    for label, reasoning in reasonings.items():
        out += ["", f"### {label}"]
        if reasoning is None or not reasoning.available:
            note = getattr(reasoning, "note", None) or "not run"
            out.append(f"_No reasoning: {note}._")
            continue
        if reasoning.narrative:
            out.append(reasoning.narrative.strip())
        for (liability, strategy_id), text in reasoning.rationales.items():
            out.append(f"- **{liability} / {strategy_id}:** {text.strip()}")
        cleared = sum(1 for c in reasoning.checks if c.passed)
        out.append(f"_Checks: {cleared}/{len(reasoning.checks)} cleared._")
    return "\n".join(out)
