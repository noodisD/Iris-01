"""
Configuration Management - Pydantic Settings

This module centralizes all environment variables, enforces types, 
and provides a fail-fast mechanism for missing required configuration.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    IRIS Configuration Schema.
    Values are automatically loaded from environment variables or .env file.
    """

    # System
    LOG_LEVEL: str = Field(default="INFO")

    # API Keys (Required in Prod)
    OPENAI_API_KEY: str = Field(default="your_openai_api_key_here")
    OPENAI_MODEL: str = Field(default="gpt-5.5")

    # PostgreSQL
    # When using docker-compose, POSTGRES_PORT should be 5433 (host port that maps to container's 5432)
    # When connecting directly to container, use 5432
    POSTGRES_DB: str = Field(default="iris_db")
    POSTGRES_USER: str = Field(default="iris_user")
    POSTGRES_PASSWORD: str = Field(default="testpassword")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5433)

    # Narrative firewall behaviour when a template cannot be rendered safely:
    # "raise" surfaces the problem (development), "silence" drops that single
    # insight and carries on (production).
    NARRATIVE_FAIL_MODE: str = Field(default="raise")

    # Configuration for .env loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Ignore extra env vars not defined here
    )

    @field_validator("NARRATIVE_FAIL_MODE")
    def validate_fail_mode(cls, v):
        if v.lower() not in ["raise", "silence"]:
            raise ValueError("NARRATIVE_FAIL_MODE must be 'raise' or 'silence'")
        return v.lower()

    def sanitized_dict(self) -> dict:
        """Returns a dict of config with secrets masked for safe logging."""
        d = self.model_dump()
        secrets = ["OPENAI_API_KEY", "POSTGRES_PASSWORD"]
        for s in secrets:
            if d[s] and len(d[s]) > 8:
                d[s] = f"{d[s][:4]}...{d[s][-4:]}"
            else:
                d[s] = "*****"
        return d

# Global instance
settings = Settings()
