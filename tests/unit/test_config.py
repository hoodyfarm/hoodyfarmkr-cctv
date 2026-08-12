import pytest
from src.config import Settings, settings

def test_default_settings():
    assert settings.APP_NAME == "hoodyfarmkr-cctv"
    assert settings.PORT == 8000
    assert settings.GEMINI_MODEL == "gemini-2.5-flash"
    assert settings.POSTGRES_USER == "postgres"
    assert settings.POSTGRES_DB == "cctv_db"

def test_async_database_url_property():
    s = Settings(
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="testpass",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5432,
        POSTGRES_DB="testdb"
    )
    assert s.get_database_url == "postgresql+asyncpg://testuser:testpass@127.0.0.1:5432/testdb"

def test_custom_database_url_override():
    custom_url = "postgresql+asyncpg://admin:secret@remotehost:5433/production_cctv"
    s = Settings(DATABASE_URL=custom_url)
    assert s.get_database_url == custom_url

def test_masked_credentials_safety():
    assert hasattr(settings, "ONVIF_PASSWORD")
    assert hasattr(settings, "GEMINI_API_KEY")
