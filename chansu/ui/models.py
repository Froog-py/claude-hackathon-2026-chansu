"""Screen fragment: connect-a-model setup. Shows each backend's status and lets the user edit an
endpoint or add a new one. Secrets are NEVER entered here — the panel only reports whether the env
key is present and points the user to set it. This module arranges and displays only (chansu-design).
"""
from __future__ import annotations

import html

import streamlit as st

from ..reasoning import registry
from . import state

_STATUS = {
    "ready": ("var(--pass)", "ready"),
    "no_key": ("var(--ink-3)", "key not set"),  # a calm not-yet state, not a critical (red) flag
    "unconfigured": ("var(--ink-3)", "unconfigured"),
}


def _status_row(entry, status) -> None:
    colour, label = _STATUS.get(status, ("var(--ink-3)", status))
    key_hint = (f" · set <code>{html.escape(entry.api_key_env)}</code> in .env"
                if status == "no_key" and entry.api_key_env else "")
    base = f" · {html.escape(entry.base_url)}" if entry.base_url else ""
    st.markdown(
        f"<div style='margin-top:8px'><span style='font-weight:600;color:var(--ink)'>{html.escape(entry.label)}</span> "
        f"<span style='font-family:var(--font-mono);font-size:11px;color:{colour}'>{label}</span>"
        f"<span class='cs-sub'>{key_hint}</span></div>"
        f"<div style='font-family:var(--font-mono);font-size:11px;color:var(--ink-3)'>{html.escape(entry.model)}{base}</div>",
        unsafe_allow_html=True,
    )


def render_model_setup() -> None:
    st.markdown("<div class='cs-sub'>Keys live in your environment (a .env file), never in the app. "
                "Endpoints and model names are set here.</div>", unsafe_allow_html=True)
    for entry, status in state.model_entries():
        _status_row(entry, status)

    with st.expander("Edit or add an endpoint"):
        eid = st.text_input("Id", key="mdl_id", placeholder="local  (or a new slug, e.g. perplexity)")
        label = st.text_input("Label", key="mdl_label", placeholder="Local (Qwen)")
        base_url = st.text_input("Base URL", key="mdl_url", placeholder="http://192.168.1.242:11434/v1")
        model = st.text_input("Model", key="mdl_model", placeholder="qwen2.5:14b-instruct")
        api_key_env = st.text_input("API key env var (blank if none)", key="mdl_env", placeholder="OPENAI_API_KEY")
        if st.button("Save endpoint", type="primary", disabled=not (eid and base_url and model)):
            registry.save_endpoint(eid.strip(), (label or eid).strip(), base_url.strip(), model.strip(),
                                   (api_key_env.strip() or None))
            st.markdown(f"<div class='cs-pass'>Saved <b>{html.escape(eid)}</b>. Select it on the Design-memo page.</div>",
                        unsafe_allow_html=True)
