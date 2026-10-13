"""Settings, read once at startup from the environment (and a .env file in development)."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NTK_", extra="ignore")

    # Which detector finds the personal information. Changing it is a .env edit and a restart.
    detector: Literal["regex", "presidio", "gliner", "regex+gliner"] = "regex"
    gliner_model: str = "urchade/gliner_multi_pii-v1"
    gliner_threshold: float = Field(0.5, ge=0.0, le=1.0)

    # Limits on what a user can send us.
    max_upload_mb: int = Field(10, ge=1, le=100)
    max_pages: int = Field(30, ge=1, le=500)

    log_level: str = "INFO"

    # The git commit this image was built from (set by the Dockerfile from the CI build); "dev" when run from source.
    commit: str = "dev"


settings = Settings()
