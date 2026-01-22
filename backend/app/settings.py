from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # If backend/.env exists, load it. Docker Compose env vars still override it.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+psycopg2://obs:obs@localhost:5432/obs"
    API_KEY: str = "dev-key"

    # Comma-separated in env, but we'll parse into a list for the app.
    CORS_ORIGINS: str = "http://localhost:3000"

    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
