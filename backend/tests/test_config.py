from layan_engine.config import Settings


def test_default_settings():
    s = Settings(ai_api_key="test-key")
    assert s.ai_provider == "deepseek"
    assert s.backend_host == "127.0.0.1"
    assert s.backend_port == 8000
    assert s.app_timezone == "Asia/Kuala_Lumpur"
    assert s.browser_headless is False


def test_provider_choice():
    s = Settings(ai_provider="openai", ai_api_key="test-key")
    assert s.ai_provider == "openai"
