from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Application"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    MONGODB_URI: str = ""
    DATABASE_NAME: str = "GEOs"

    MONGODB_URI: str = ""
    DATABASE_NAME: str = "GEOs"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()