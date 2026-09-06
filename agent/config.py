"""
Configuration Management - Pydantic Settings

This module centralizes all environment variables, enforces types, 
and provides a fail-fast mechanism for missing required configuration.
"""

import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    """
    IRIS Configuration Schema.
    Values are automatically loaded from environment variables or .env file.
    """
    
    # System
    ENV: str = Field(default="dev")
    LOG_LEVEL: str = Field(default="INFO")
    
    # API Keys (Required in Prod)
    OPENAI_API_KEY: str = Field(default="your_openai_api_key_here")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini")
    
    # PostgreSQL
    # When using docker-compose, POSTGRES_PORT should be 5433 (host port that maps to container's 5432)
    # When connecting directly to container, use 5432
    POSTGRES_DB: str = Field(default="iris_db")
    POSTGRES_USER: str = Field(default="iris_user")
    POSTGRES_PASSWORD: str = Field(default="testpassword")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5433)

    # Analytical Defaults
    DEFAULT_MIN_CONFIDENCE: str = Field(default="medium")
    DEFAULT_MAX_CONTEXT_ITEMS: int = Field(default=5)
    
    # Feature Flags
    CONFLICT_SUPPRESSION_ENABLED: bool = Field(default=True)
    NARRATIVE_FAIL_MODE: str = Field(default="raise")
    CHROMADB_TELEMETRY: bool = Field(default=False)

    # Configuration for .env loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Ignore extra env vars not defined here
    )

    @field_validator("ENV")
    def validate_env(cls, v):
        if v.lower() not in ["dev", "prod", "test"]:
            raise ValueError("ENV must be dev, prod, or test")
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
