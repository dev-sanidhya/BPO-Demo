from functools import lru_cache

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

    def validate_runtime(self) -> None:
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
