"""Chansu — Streamlit entry point (spec: Day-5 UI).

Run from the repo root:  ``.venv/bin/streamlit run chansu/ui/app.py``

Streamlit puts the *script's* directory on ``sys.path`` (not the repo root), so ``import chansu …`` would
fail; the bootstrap below adds the repo root. The CLI (``python -m chansu.cli``) is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

# --- bootstrap: make `import chansu ...` work when run as a bare Streamlit script ---
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load a local .env so API keys are picked up from a gitignored file (keys never live in code or git).
try:
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

import streamlit as st  # noqa: E402

from chansu.ui import state, theme  # noqa: E402
from chansu.ui.ingest import render_ingest  # noqa: E402
from chansu.ui.memo import render_memo_tab  # noqa: E402
from chansu.ui.sources import render_sources  # noqa: E402
from chansu.ui.workspace import render_workspace  # noqa: E402

_LOGO = _REPO_ROOT / "logo-chansu-dark.png"
_MARK = Path(__file__).resolve().parent / "assets" / "mark.png"
_GITHUB = "https://github.com/Froog-py/claude-hackathon-2026-chansu"
_LINKEDIN = "https://www.linkedin.com/in/luke-kerner-25fus/"

st.set_page_config(page_title="Chansu", page_icon=str(_MARK) if _MARK.exists() else "⬡", layout="wide")
theme.inject()


@st.dialog("About Chansu")
def _about() -> None:
    st.markdown(
        "**Chansu** helps a medicinal chemist take a natural compound with known activity but a "
        "liability that blocks its use as a drug, then generate **grounded, citation-backed hypotheses** "
        "for how to modify it. It matches each liability to precedent-backed strategies, generates "
        "chemically-valid analogs, and computes their properties behind a strict trust boundary. "
        "Claude reasons and retrieves. RDKit computes and validates. Every claim is provenance-tagged.\n\n"
        "The engine is compound-agnostic: adding a compound is data only, never a code change. A "
        "flagship compound shows depth. A second, structurally different one proves generality.\n\n"
        "Built for the **Built with Claude: Life Sciences** hackathon (partnered with the Gladstone "
        "Institutes)."
    )
    st.markdown(f"[GitHub repo]({_GITHUB}) · [Luke Kerner on LinkedIn]({_LINKEDIN})")


def _sidebar():
    with st.sidebar:
        if _LOGO.exists():
            st.image(str(_LOGO), use_container_width=True)
        else:
            st.title("Chansu")
        st.caption("Grounded modification hypotheses for natural compounds.")

        ids = state.available_compound_ids()
        default = state.default_compound_id()
        index = ids.index(default) if default in ids else 0
        compound_id = st.selectbox("Compound", ids, index=index, format_func=lambda s: s.replace("_", " ").title())

        st.markdown("<p class='cs-eyebrow' style='margin-bottom:2px'>Reasoning depth</p>", unsafe_allow_html=True)
        if "depth" not in st.session_state:
            st.session_state["depth"] = "strategy"
        st.segmented_control(
            "Reasoning depth",
            ["strategy", "compound"],
            key="depth",
            label_visibility="collapsed",
            format_func=lambda d: "Strategy" if d == "strategy" else "Compound",
            help="Strategy-level is the safe default. Compound-specific is richer but trips safety classifiers "
                 "on sensitive compounds and falls back to strategy-level.",
        )

        st.divider()
        from chansu.ui.models import render_model_setup
        with st.expander("Models"):
            render_model_setup()

        if st.button("About", use_container_width=True):
            _about()
    return compound_id


def main() -> None:
    compound_id = _sidebar()
    compound, result = state.get_design(compound_id)
    mol = state.mol_for(compound)

    workspace_tab, memo_tab, sources_tab, ingest_tab = st.tabs(
        ["Workspace", "Design memo", "Sources / Reference", "Add compound"]
    )
    with workspace_tab:
        render_workspace(compound, mol, result)
    with memo_tab:
        render_memo_tab(compound, mol, result)
    with sources_tab:
        render_sources(compound, state.get_strategies())
    with ingest_tab:
        render_ingest(state.get_strategies())


main()
