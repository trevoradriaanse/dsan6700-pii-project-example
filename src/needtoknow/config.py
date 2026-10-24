"""Settings, read once at startup from the environment (and a .env file in development)."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NTK_", extra="ignore")

    # Which detector finds the personal information. Changing it is a .env edit and a restart.
    detector: Literal["regex", "presidio", "gliner", "regex+gliner"] = "regex"
    gliner_model: str = "urchade/gliner_multi_pii-v1"
    # The exact commit of the weights on Hugging Face. uv.lock pins our packages, not the model we download by name.
    gliner_revision: str = "1fcf13e85f4eef5394e1fcd406cf2ca9ea82351d"
    gliner_threshold: float = Field(0.5, ge=0.0, le=1.0)

    # Limits on what a user can send us.
    max_upload_mb: int = Field(10, ge=1, le=100)
    max_pages: int = Field(30, ge=1, le=500)

    # Uploads (find or redact) one client may send per minute; 0 turns the limit off.
    rate_limit_per_minute: int = Field(30, ge=0)

    log_level: str = "INFO"

    # Where the usage counts live (a SQLite file on a volume); empty means do not count.
    db_path: str = ""

    # The key for the /admin routes, sent in an X-Admin-Key header. Empty turns those routes off (404).
    # SecretStr keeps it out of logs and tracebacks: printing the settings shows "**********".
    admin_api_key: SecretStr = SecretStr("")

    # The git commit this image was built from (set by the Dockerfile from the CI build); "dev" when run from source.
    commit: str = "dev"


settings = Settings()
