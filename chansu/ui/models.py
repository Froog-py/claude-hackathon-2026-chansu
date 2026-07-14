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
    entries = state.model_entries()
    for entry, status in entries:
        _status_row(entry, status)

    by_id = {e.id: e for e, _ in entries}
    with st.expander("Edit or add an endpoint"):
        eid = st.text_input("Id", key="mdl_id", placeholder="local  (or a new slug, e.g. perplexity)")
        cur = by_id.get(eid.strip())
        if cur is not None:  # editing an existing entry: show its current values (blank = keep)
            mono = "font-family:var(--font-mono)"  # machine data in mono, matching the status rows (§3)
            key_desc = (f"key env <span style='{mono}'>{html.escape(cur.api_key_env)}</span>"
                        if cur.api_key_env else "keyless")
            st.markdown(
                f"<div class='cs-sub'>Editing <b>{html.escape(cur.id)}</b>. Current: {html.escape(cur.label)} · "
                f"<span style='{mono}'>{html.escape(cur.model)}</span> · "
                f"<span style='{mono}'>{html.escape(cur.base_url or '(none)')}</span> · {key_desc}. "
                "Leave a field blank to keep its current value.</div>",
                unsafe_allow_html=True)
        label = st.text_input("Label", key="mdl_label", placeholder="Local (Qwen)")
        base_url = st.text_input("Base URL", key="mdl_url", placeholder="http://<host>:11434/v1")
        model = st.text_input("Model", key="mdl_model", placeholder="qwen2.5:14b-instruct")
        api_key_env = st.text_input("API key env var (blank if none)", key="mdl_env", placeholder="OPENAI_API_KEY")

        # Strip once and reuse (no whitespace-only saves). A blank field keeps the current entry's value,
        # so tweaking a built-in's base_url never wipes its label or key-env; a new id starts from blanks.
        eid_s, label_s, url_s, model_s, env_s = (
            eid.strip(), label.strip(), base_url.strip(), model.strip(), api_key_env.strip())
        final_label = label_s or (cur.label if cur else eid_s)
        final_url = url_s or (cur.base_url if cur else "")
        final_model = model_s or (cur.model if cur else "")
        final_env = env_s or (cur.api_key_env if cur else None)
        if st.button("Save endpoint", type="primary", disabled=not (eid_s and final_url and final_model)):
            if final_env and final_url.lower().startswith("http://"):
                st.markdown(
                    "<div class='cs-declined'>An http:// endpoint with an API key would send the key in "
                    "cleartext. Use https for a keyed endpoint (http is fine for a keyless local model).</div>",
                    unsafe_allow_html=True)
            else:
                registry.save_endpoint(eid_s, final_label, final_url, final_model, final_env)
                st.markdown(f"<div class='cs-pass'>Saved <b>{html.escape(eid_s)}</b>. Select it on the "
                            "Design-memo page.</div>", unsafe_allow_html=True)
