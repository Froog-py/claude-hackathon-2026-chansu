"""Pure-Python prompt builder for the Claude Science import path (Path A). No model, no network: it
emits the one-time Claude Science project setup and a per-compound review prompt that asks for
exactly the record the ingest gate validates. Generic (PROJECT.md §5): the text names no specific
compound; the controlled vocabulary is injected by the caller from the loaded library.
"""
from __future__ import annotations

from typing import Optional

PROJECT_NAME = "Chansu Compound Grounding"

PROJECT_DESCRIPTION = (
    "Extraction of grounded, citation-backed structured records for medicinal-chemistry compounds, "
    "for import into Chansu (a generic compound-modification tool). For a named natural compound with "
    "known therapeutic activity, produce its molecular targets, druggability liabilities, "
    "activity-essential regions, and modifiable handles, each backed by a real, PubMed-verifiable "
    "citation. Never fabricate a citation, a structure, or a number. Where a fact cannot be grounded, "
    "leave it empty and say so."
)

AGENT_CONTEXT = (
    "You extract structured compound records for Chansu, a medicinal-chemistry tool with a strict "
    "trust boundary: literature is grounded and cited; structures and properties are computed "
    "deterministically downstream; every claim is provenance-tagged. Your job is the literature "
    "grounding only.\n\n"
    "For the compound you are given, identify its molecular target(s) and role; its druggability "
    "liabilities (for example toxicity, poor solubility, rapid clearance, poor selectivity); the "
    "regions essential for activity, graded high / medium / low; and the positions that are "
    "reasonable medicinal-chemistry handles to modify. Back every target, liability, and importance "
    "claim with a real citation carrying a PMID and/or DOI that resolves on PubMed. Prefer primary "
    "literature. Do not invent authors, years, identifiers, or numbers; if you are unsure a citation "
    "is real, omit it. Provide a canonical SMILES from a named source (for example PubChem, with the "
    "CID), not from memory. Do not predict binding affinity, toxicity, or efficacy, and do not claim "
    "a liability is solved: you ground facts; the tool reasons and computes. Where a field cannot be "
    "grounded, leave it empty and note what is missing. An honest gap is correct; a fabricated fill "
    "is a failure."
)

RECORD_SCHEMA = """{
  "id": "<slug, lowercase_with_underscores>",
  "name": "<display name>",
  "structure": {"smiles": "<canonical SMILES>", "source": "PubChem", "source_id": "CID <n>", "inchikey": "<key>"},
  "targets": [{"name": "<target>", "role": "<role>", "citation": {"label": "<full citation>", "source": "PMID <n> | DOI <doi>"}}],
  "liabilities": [{"kind": "<liability kind>", "detail": "<detail>", "citation": {"label": "<full citation>", "source": "PMID <n> | DOI <doi>"}}],
  "importance_map": [{"id": "<slug>", "importance": "high|medium|low", "reason": "<why>", "locator": {"smarts": "<SMARTS>", "label": "<label>"}, "citation": {"label": "<full citation>", "source": "PMID <n>"}}],
  "modifiable_positions": [{"id": "<slug>", "label": "<label>", "attachment_types": ["<type>"], "locator": {"smarts": "<SMARTS>", "label": "<label>"}}],
  "gaps": ["<anything you could not ground with a real citation>"]
}"""


def build_project_setup() -> str:
    """The one-time text pasted into a Claude Science project's settings (permanent)."""
    return (
        f"Project name:\n{PROJECT_NAME}\n\n"
        f"Project description:\n{PROJECT_DESCRIPTION}\n\n"
        f"Agent context:\n{AGENT_CONTEXT}\n"
    )


def build_review_prompt(name: str, vocabulary: tuple, liability_focus: Optional[str] = None) -> str:
    """The per-compound prompt the chemist pastes into Claude Science. ``vocabulary`` is
    ``(attachment_types, liability_classes)`` from the loaded library (``ingest.derive_vocabulary``)."""
    attach, liab = vocabulary
    focus = f" Focus especially on the liability: {liability_focus}." if liability_focus else ""
    return (
        f"Produce a Chansu compound record for {name}.{focus}\n\n"
        "Ground and return: a canonical SMILES with its source (for example a PubChem CID) and InChIKey "
        "if available; molecular targets (name + role), druggability liabilities (kind + detail), and "
        "activity-essential regions graded high / medium / low (reason + locator SMARTS), each backed by "
        "a real PMID/DOI citation; and modifiable positions (label + attachment type + locator SMARTS).\n\n"
        "Emit exactly this JSON, filling every field you can ground and listing anything you cannot "
        f'under "gaps":\n{RECORD_SCHEMA}\n\n'
        f"Controlled vocabulary. Attachment types: {sorted(attach)}. Liability kinds: {sorted(liab)}. "
        "Use these where they fit so the record lines up with the strategy library.\n\n"
        "Rules: real citations only, verifiable on PubMed (PMID and/or DOI); no invented authors, "
        "years, or numbers; SMILES from a named source, not memory; do not predict binding, toxicity, "
        'or efficacy. If a fact cannot be grounded, leave it empty and say so under "gaps".'
    )
