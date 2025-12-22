from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://obs:obs@localhost:5432/obs"
    API_KEY: str = "dev-key"
    CORS_ORIGINS: str = "http://localhost:5173"

settings = Settings()
