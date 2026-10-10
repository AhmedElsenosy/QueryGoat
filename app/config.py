from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SRC_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SRC_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "QueryGoat"
    database_url: str


settings = Settings()
