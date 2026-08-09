from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLATFORM_", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./bpo-platform.db"
    jwt_secret: str = "development-only-change-me"
    jwt_minutes: int = 480
    seed_demo: bool = True
    seed_admin_email: str = "admin@pilot.example"
    seed_admin_password: str = "ChangeMe123!"
    seed_chat_widget_key: str = "pilot-widget-key-change-me"
    default_ai_mode: Literal["external", "local"] = "external"
    cors_origins: str = "http://localhost:4173,http://localhost:5173"
    recording_dir: str = "/data/recordings"
    voice_fixture_path: str = "/fixtures/deterministic-pilot.wav"
    voice_fixture_manifest_path: str = "/fixtures/deterministic-pilot.json"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_realtime_asr_model: str = "whisper-large-v3"
    groq_final_asr_model: str = "whisper-large-v3"
    groq_guidance_model: str = "openai/gpt-oss-20b"
    groq_qa_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = 60.0
    usd_to_inr: float = 84.0

    def validate_runtime(self) -> None:
        if self.default_ai_mode == "external" and not self.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required because external AI is the default processing route")
        if self.environment != "development" and self.jwt_secret == "development-only-change-me":
            raise RuntimeError("PLATFORM_JWT_SECRET must be set outside development")
        if self.environment != "development" and self.seed_admin_password == "ChangeMe123!":
            raise RuntimeError("PLATFORM_SEED_ADMIN_PASSWORD must be changed outside development")
        if self.environment != "development" and self.seed_chat_widget_key == "pilot-widget-key-change-me":
            raise RuntimeError("PLATFORM_SEED_CHAT_WIDGET_KEY must be changed outside development")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
