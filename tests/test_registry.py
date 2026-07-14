"""Tests for the reasoning model registry (built-ins, env-derived status, gitignored config)."""
import pytest

from chansu.reasoning import registry
from chansu.reasoning.adapter import ClaudeReasoningModel
from chansu.reasoning.openai_compatible import OpenAICompatibleReasoningModel

# RFC 5737 TEST-NET-1: a documentation-reserved address, used in place of any real LAN IP.
_EXAMPLE_LOCAL = "http://192.0.2.10:11434/v1"


def test_builtins_present_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    ids = {e.id for e in registry.load_registry()}
    assert {"claude", "openai", "local"} <= ids


def test_status_reflects_env(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    entries = {e.id: e for e in registry.load_registry()}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert registry.status(entries["claude"]) == "no_key"
    assert registry.status(entries["openai"]) == "no_key"
    assert registry.status(entries["local"]) == "ready"  # keyless + has base_url
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert registry.status(entries["claude"]) == "ready"


def test_build_model_types(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    entries = {e.id: e for e in registry.load_registry()}
    assert isinstance(registry.build_model(entries["claude"]), ClaudeReasoningModel)
    assert isinstance(registry.build_model(entries["local"]), OpenAICompatibleReasoningModel)


def test_save_and_load_endpoint_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    registry.save_endpoint("perplexity", "Perplexity", "https://api.perplexity.ai", "sonar", "PPLX_API_KEY")
    entries = {e.id: e for e in registry.load_registry()}
    assert "perplexity" in entries and entries["perplexity"].base_url == "https://api.perplexity.ai"


def test_local_base_url_override(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    registry.save_endpoint("local", "Local", _EXAMPLE_LOCAL, "qwen2.5:14b-instruct")
    local = {e.id: e for e in registry.load_registry()}["local"]
    assert local.base_url == _EXAMPLE_LOCAL


def test_builtin_label_and_key_env_overrides_apply(monkeypatch, tmp_path):
    # A built-in's label and api_key_env are honored from the persisted config, not just base_url/model.
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    registry.save_endpoint("openai", "My GPT", "https://api.openai.com/v1", "gpt-4o", "MY_OPENAI_KEY")
    entry = {e.id: e for e in registry.load_registry()}["openai"]
    assert entry.label == "My GPT"
    assert entry.api_key_env == "MY_OPENAI_KEY"
    # ...and status follows the overridden key env, not the built-in default.
    monkeypatch.delenv("MY_OPENAI_KEY", raising=False)
    assert registry.status(entry) == "no_key"
    monkeypatch.setenv("MY_OPENAI_KEY", "x")
    assert registry.status(entry) == "ready"


def test_save_rejects_http_endpoint_carrying_a_key(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    with pytest.raises(ValueError):
        registry.save_endpoint("insecure", "Insecure", "http://api.example.com/v1", "m", "SECRET_KEY")


def test_save_allows_keyless_http_and_keyed_https(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    registry.save_endpoint("localx", "LocalX", _EXAMPLE_LOCAL, "qwen2.5:14b-instruct", None)  # keyless http OK
    registry.save_endpoint("secure", "Secure", "https://api.example.com/v1", "m", "SECRET_KEY")  # https + key OK
    ids = {e.id for e in registry.load_registry()}
    assert {"localx", "secure"} <= ids


def test_malformed_config_degrades_to_builtins(monkeypatch, tmp_path):
    cfg = tmp_path / "models.local.json"
    cfg.write_text("{ this is not valid json ]")
    monkeypatch.setattr(registry, "_CONFIG", cfg)
    ids = {e.id for e in registry.load_registry()}
    assert {"claude", "openai", "local"} <= ids  # built-ins survive a corrupt local file


def test_malformed_user_entry_is_skipped_not_fatal(monkeypatch, tmp_path):
    cfg = tmp_path / "models.local.json"
    # a good user entry alongside a malformed one (missing base_url/model)
    cfg.write_text('{"good": {"label": "Good", "base_url": "https://api.example.com/v1", "model": "m"}, '
                   '"bad": {"label": "Bad"}}')
    monkeypatch.setattr(registry, "_CONFIG", cfg)
    ids = {e.id for e in registry.load_registry()}
    assert "good" in ids and "bad" not in ids
