"""Cached access to the deterministic pipeline and the reasoning backend (spec: "Data flow & caching").

Streamlit re-runs the whole script on every interaction, so the fast/pure deterministic work is cached
(keyed on the compound id, a string) and rendered instantly and offline; the slow, sometimes-refusing
Claude call is NOT cached here — it is run explicitly by a button and stored in ``session_state`` by the
memo screen. The ``Mol`` is recomputed per run (cheap ``MolFromSmiles``) rather than cached, so nothing
here depends on RDKit object pickling.
"""

from __future__ import annotations

import streamlit as st

from ..core.loaders import DEFAULT_DATA_DIR, load_compound, load_config, load_strategies, to_mol
from ..core.pipeline import design
from ..reasoning.adapter import ClaudeReasoningModel


@st.cache_data(show_spinner=False)
def available_compound_ids() -> list:
    """Every compound with a data file — the selector's options. A new compound dropped into
    ``data/compounds/`` appears here automatically (the §5 acceptance test, live)."""
    directory = DEFAULT_DATA_DIR / "compounds"
    return sorted(p.stem for p in directory.glob("*.json"))


@st.cache_data(show_spinner=False)
def default_compound_id() -> str:
    return load_config().get("demo_compound") or (available_compound_ids() or [""])[0]


@st.cache_data(show_spinner=False)
def get_design(compound_id: str):
    """The deterministic design bundle ``(compound, result)`` — cached, picklable, network-free.
    Callers recompute ``mol`` with :func:`mol_for` (cheap) rather than caching an RDKit object."""
    compound = load_compound(compound_id)
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())
    return compound, result


@st.cache_data(show_spinner=False)
def get_strategies() -> list:
    return load_strategies()


def mol_for(compound):
    """RDKit mol for a compound — recomputed per run (not cached; cheap ``MolFromSmiles``)."""
    return to_mol(compound)


@st.cache_resource(show_spinner=False)
def get_reasoning_model() -> ClaudeReasoningModel:
    """One reasoning backend for the session. Construction reads no credentials — a missing key/backend
    only surfaces when the memo screen actually runs a call, where it degrades honestly."""
    return ClaudeReasoningModel(effort="medium")
