"""
Configuration Management - Pydantic Settings

This module centralizes all environment variables, enforces types,
and provides a fail-fast mechanism for missing required configuration.
"""

from ipaddress import ip_address, ip_network

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    IRIS Configuration Schema.
    Values are automatically loaded from environment variables or .env file.
    """

    # System
    LOG_LEVEL: str = Field(default="INFO")
    # Uploads, extracted exports and kept audio. Relative paths resolve against
    # the project root; `data/` is already gitignored.
    DATA_DIR: str = Field(default="data")

    # API Keys (Required in Prod)
    OPENAI_API_KEY: str = Field(default="your_openai_api_key_here")
    # What the owner reads: chat, the weekly letter, the questions an inquiry
    # asks. Quality is the whole point here.
    OPENAI_MODEL: str = Field(default="gpt-5.5")
    # The mechanical passes: labelling an account against a circumstance,
    # saying where a dictated sentence ends. Classification and routing, where
    # a cheap model is the intended tool rather than a compromise — and where
    # the work is checked by construction or by counting, not taken on trust.
    # luna is a tenth of terra's input price and a twenty-fifth of sol's.
    OPENAI_WORKER_MODEL: str = Field(default="gpt-5.6-luna")
    # Any OpenAI-compatible endpoint: Ollama, llama.cpp's server, vLLM, or
    # another provider. Empty means OpenAI itself. The reason to set it is not
    # price — the counting passes already cost pennies — but that a local
    # endpoint keeps the archive on this machine, which is the constraint the
    # rest of this product is built around.
    OPENAI_BASE_URL: str = Field(default="")
    # Accuracy matters more than cost here: a transcript becomes a reflection,
    # gets embedded, and is quoted back as something the owner said, so a
    # mis-heard word turns into evidence. gpt-4o-mini-transcribe is the cheaper
    # lever for a very large backlog; whisper-1 is the one to switch to if
    # per-segment timestamps are ever wanted.
    TRANSCRIPTION_MODEL: str = Field(default="gpt-4o-transcribe")

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

    # Configuring an interface explicitly opts in to the TLS listener. Pairing
    # controls admission on that listener; it never binds a new interface.
    LAN_BIND_HOST: str = Field(default="")
    LAN_BIND_PORT: int = Field(default=8765, ge=1024, le=65535)
    LAN_BIND_ENABLED: bool = Field(default=False)
    MOBILE_BEARER_HASH: str | None = Field(default=None)
    # Populated by the two-listener launcher only after TLS starts.
    LAN_URL: str | None = Field(default=None, exclude=True)
    LAN_PUBLIC_KEY_SHA256: str | None = Field(default=None, exclude=True)
    # Why the configured phone listener is not serving; set by scripts/serve_iris.py.
    LAN_LISTENER_ERROR: str | None = Field(default=None, exclude=True)


    # Configuration for .env loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Ignore extra env vars not defined here
    )

    @field_validator("LAN_BIND_HOST")
    @classmethod
    def validate_lan_host(cls, host: str) -> str:
        if not host:
            return host
        try:
            address = ip_address(host)
        except ValueError as exc:
            raise ValueError("LAN_BIND_HOST must be a private IPv4 address") from exc
        if address.version != 4 or not any(address in network for network in (
            ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
        )):
            raise ValueError("LAN_BIND_HOST must be a private IPv4 address")
        return str(address)

    @field_validator("NARRATIVE_FAIL_MODE")
    def validate_fail_mode(cls, v):
        if v.lower() not in ["raise", "silence"]:
            raise ValueError("NARRATIVE_FAIL_MODE must be 'raise' or 'silence'")
        return v.lower()

    def sanitized_dict(self) -> dict:
        """Returns a dict of config with secrets masked for safe logging."""
        d = self.model_dump()
        secrets = ["OPENAI_API_KEY", "POSTGRES_PASSWORD", "MOBILE_BEARER_HASH"]
        for s in secrets:
            if d[s] and len(d[s]) > 8:
                d[s] = f"{d[s][:4]}...{d[s][-4:]}"
            else:
                d[s] = "*****"
        return d

# Global instance
settings = Settings()
