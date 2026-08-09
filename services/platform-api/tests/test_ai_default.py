import pytest

from app.config import Settings


def test_external_ai_is_the_default_and_requires_a_provider_key() -> None:
    settings = Settings(_env_file=None, groq_api_key="")

    assert settings.default_ai_mode == "external"
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is required"):
        settings.validate_runtime()


def test_strict_local_mode_remains_an_explicit_fallback() -> None:
    settings = Settings(_env_file=None, default_ai_mode="local", groq_api_key="")

    settings.validate_runtime()
    assert settings.default_ai_mode == "local"
