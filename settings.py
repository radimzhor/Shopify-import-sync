"""
Pydantic-based configuration management for the Mergado app.
Provides type-safe environment variable loading and validation.
"""
from typing import Optional

from pydantic import field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    model_config = ConfigDict(extra='ignore', env_file='.env', case_sensitive=False)

    # Flask configuration
    flask_secret_key: str = "dev-secret-key-change-in-production"
    flask_env: str = "development"
    flask_debug: bool = False

    # Mergado OAuth configuration
    mergado_client_id: Optional[str] = None
    mergado_client_secret: Optional[str] = None
    mergado_redirect_uri: str = "http://localhost:5000/callback"
    mergado_auth_url: str = "https://app.mergado.com/oauth2/authorize"
    mergado_token_url: str = "https://app.mergado.com/oauth2/token"
    mergado_api_base_url: str = "https://api.mergado.com"

    # Database configuration (SQLite for simplicity, can be extended)
    database_url: str = "sqlite:///mergado_app.db"

    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 5000


    @field_validator("flask_debug", mode='before')
    @classmethod
    def parse_debug(cls, v):
        """Parse debug setting from string or boolean."""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return v

    @field_validator("port", mode='before')
    @classmethod
    def parse_port(cls, v):
        """Parse port from string to int."""
        if isinstance(v, str):
            return int(v)
        return v


# Global settings instance
settings = Settings()
