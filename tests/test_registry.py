"""Tests for the reasoning model registry (built-ins, env-derived status, gitignored config)."""
from chansu.reasoning import registry
from chansu.reasoning.adapter import ClaudeReasoningModel
from chansu.reasoning.openai_compatible import OpenAICompatibleReasoningModel


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
    registry.save_endpoint("local", "Local", "http://192.168.1.242:11434/v1", "qwen2.5:14b-instruct")
    local = {e.id: e for e in registry.load_registry()}["local"]
    assert local.base_url == "http://192.168.1.242:11434/v1"
