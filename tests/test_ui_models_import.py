"""Behavioral tests for the connect-a-model UI (`render_model_setup`). Uses Streamlit's AppTest so
the status rendering, the non-destructive edit, and the http+key guard are exercised without a
browser. `registry._CONFIG` is pointed at a tmp file so the built-ins (and only the built-ins) load.
"""
from streamlit.testing.v1 import AppTest

from chansu.reasoning import registry


def _render():
    # The script AppTest runs: render the panel on its own (the real app wraps it in a sidebar expander).
    from chansu.ui.models import render_model_setup

    render_model_setup()


def _markdown_blob(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_render_model_setup_importable():
    from chansu.ui import models as ui_models

    assert hasattr(ui_models, "render_model_setup")


def test_lists_backends_with_status(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_function(_render).run()
    assert not at.exception
    blob = _markdown_blob(at)
    assert "Claude" in blob and "ChatGPT" in blob and "Local" in blob
    assert "key not set" in blob   # claude + openai: no env key
    assert "ready" in blob         # local: keyless + has base_url


def test_editing_existing_id_shows_caption_and_save_is_non_destructive(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    at = AppTest.from_function(_render).run()
    at.text_input(key="mdl_id").set_value("local").run()
    assert "Editing" in _markdown_blob(at)  # the "Editing local. Current: ..." caption
    # Save with every other field blank: local keeps its built-in base_url and model (not wiped).
    at.button[0].click().run()
    assert not at.exception
    saved = {e.id: e for e in registry.load_registry()}["local"]
    assert saved.base_url == "http://localhost:11434/v1"
    assert saved.model == "qwen2.5:14b-instruct"


def test_http_endpoint_with_key_is_refused_in_ui(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    at = AppTest.from_function(_render).run()
    at.text_input(key="mdl_id").set_value("insecure").run()
    at.text_input(key="mdl_url").set_value("http://api.example.com/v1").run()
    at.text_input(key="mdl_model").set_value("m").run()
    at.text_input(key="mdl_env").set_value("SECRET_KEY").run()
    at.button[0].click().run()
    assert not at.exception
    assert "cleartext" in _markdown_blob(at)                       # the warning is shown
    assert "insecure" not in {e.id for e in registry.load_registry()}  # nothing persisted


def test_whitespace_only_inputs_do_not_persist(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    at = AppTest.from_function(_render).run()
    at.text_input(key="mdl_id").set_value("   ").run()
    at.text_input(key="mdl_url").set_value("   ").run()
    at.text_input(key="mdl_model").set_value("   ").run()
    # A new id whose stripped value is empty leaves Save disabled; clicking is a no-op.
    assert at.button[0].disabled
    assert len(registry.load_registry()) == 3  # still just the three built-ins
