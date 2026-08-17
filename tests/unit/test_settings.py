from patient_ops_agent.clock import FixedClock, SystemClock, runtime_clock
from patient_ops_agent.settings import Settings


def test_settings_default_to_fake_provider_without_llm_secret(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "fake"
    assert settings.uses_sqlite is True
    settings.validate_llm_configuration()
    settings.validate_storage_configuration()


def test_deepseek_mode_requires_explicit_model_and_secret():
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_model=None,
    )

    try:
        settings.validate_llm_configuration()
    except ValueError as exc:
        assert "DEEPSEEK_MODEL" in str(exc)
    else:
        raise AssertionError("deepseek mode without a model must fail")


def test_local_fake_profile_uses_the_stable_demo_business_clock():
    settings = Settings(_env_file=None)

    clock = runtime_clock(settings.uses_sqlite, settings.llm_provider, settings.demo_business_clock)

    assert isinstance(clock, FixedClock)
    assert clock.now().isoformat() == "2026-08-14T09:00:00+08:00"
    assert isinstance(runtime_clock(False, "fake", settings.demo_business_clock), SystemClock)
