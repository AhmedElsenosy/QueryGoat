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
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8000/auth/google/callback"
    email_address: str = ""
    email_password: str = ""
    app_frontend_url: str = "http://localhost:3000"
    sqlite_data_dir: Path = SRC_DIR / "data" / "sqlite"
    daily_job_secret: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    # Rate limits
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_refresh: str = "10/minute"
    rate_limit_submit: str = "15/minute"


settings = Settings()
