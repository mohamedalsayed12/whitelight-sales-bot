from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Values come from the environment, then from the local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    test_database_url: str = ""
    jwt_secret: str
    jwt_expire_minutes: int = 480
    admin_email: str = ""
    admin_password: str = ""
    admin_full_name: str = "Admin"
    sample_leads: bool = True


settings = Settings()
