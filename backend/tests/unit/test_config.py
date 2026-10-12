import pytest
import yaml

from app.core import config_loader
from app.core.config_loader import CONFIG_DIR, ConfigError, read_yaml
from app.core.settings import Settings
from app.schemas.config import CarePathsConfig, ConversationConfig, FollowUpConfig, SafetyConfig, VerificationConfig


def test_shipped_configuration_is_valid():
    config_loader.validate_all()


def broken(filename: str, change) -> dict:
    data = read_yaml(CONFIG_DIR / filename)
    change(data)
    return data


def test_missing_urgency_level_is_rejected():
    data = broken("care_paths.yml", lambda d: d["levels"].pop(3))
    with pytest.raises(ValueError, match="levels must be exactly 1-5"):
        CarePathsConfig.model_validate(data)


def test_missing_translation_is_rejected():
    data = broken("conversation.yml", lambda d: d["disclaimer"].pop("en"))
    with pytest.raises(ValueError, match="missing translation"):
        ConversationConfig.model_validate(data)


def test_follow_up_categories_must_match_across_languages():
    data = broken("follow_up_questions.yml", lambda d: d["categories"]["pain"]["en"].pop())
    with pytest.raises(ValueError, match="different number of questions"):
        FollowUpConfig.model_validate(data)


def test_invalid_regex_is_rejected():
    data = broken("verification.yml", lambda d: d["dose_units"].append("(mg"))
    with pytest.raises(ValueError, match="invalid regex"):
        VerificationConfig.model_validate(data)


def test_missing_safety_message_is_rejected():
    data = broken("safety.yml", lambda d: d["messages"].pop("self_harm"))
    with pytest.raises(ValueError, match="self_harm"):
        SafetyConfig.model_validate(data)


def test_unknown_specialist_reference_is_rejected(monkeypatch, tmp_path):
    data = broken("triage.yml", lambda d: d["symptom_profiles"][0].update(specialist="cardio_typo"))
    path = tmp_path / "triage.yml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config_loader, "CONFIG_DIR", tmp_path)
    config_loader.triage.cache_clear()
    try:
        # Only triage.yml is redirected; the other files are still read from their cached copies.
        with pytest.raises(ConfigError, match="cardio_typo"):
            config_loader.validate_all()
    finally:
        config_loader.triage.cache_clear()


def test_environment_overrides_settings_file(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert Settings(_env_file=None).ollama_model == "qwen3:8b"  # from settings.yml, ignoring any .env
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    assert Settings(_env_file=None).ollama_model == "qwen3:14b"
