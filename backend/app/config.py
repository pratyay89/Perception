import secrets
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# In development, when no SECRET_KEY is configured, a random key is generated
# once and kept in this file so that logins survive a server restart. The key
# is never in the source code, and this file must not be committed or deployed.
_DEV_SECRET_FILE = Path(".dev_secret_key")


def _load_or_create_dev_secret() -> str:
    try:
        existing = _DEV_SECRET_FILE.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except OSError:
        pass

    key = secrets.token_urlsafe(48)
    try:
        _DEV_SECRET_FILE.write_text(key, encoding="utf-8")
    except OSError:
        # Read-only directory: fall back to a key that lasts for this process
        pass
    return key


class Settings(BaseSettings):
    PROJECT_NAME: str = "Perception Backend"
    VERSION: str = "1.0.0"
    API_STR: str = "/api"

    # Environment (development, production)
    ENVIRONMENT: str = "development"

    # Security
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Database URL.
    #   PostgreSQL: postgresql+asyncpg://user:password@localhost:5432/perception
    #   SQLite (zero-setup local development): sqlite+aiosqlite:///./perception.db
    DATABASE_URL: str = "sqlite+aiosqlite:///./perception.db"
    # Log every SQL statement (noisy; useful when debugging queries)
    DATABASE_ECHO: bool = False

    # Comma-separated list of origins allowed to call the API from a browser.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Generative AI integration (Groq)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Optional: point the client at another Groq-compatible endpoint.
    GROQ_BASE_URL: str = ""
    # Reasoning models only ("low", "medium", "high"). Use "none" for models
    # that do not accept the parameter.
    GROQ_REASONING_EFFORT: str = "low"
    # Budget for one evaluation (reasoning + answer). Too small truncates the JSON.
    GROQ_MAX_COMPLETION_TOKENS: int = 1024
    GROQ_TIMEOUT_SECONDS: float = 45.0
    # Retries on rate limits (429), timeouts and 5xx; the SDK honours Retry-After.
    GROQ_MAX_RETRIES: int = 3
    # How many answers are sent to the LLM at the same time. Keep this low on the
    # Groq free tier, which has a small tokens-per-minute budget.
    LLM_MAX_CONCURRENCY: int = 2

    # Monthly limits per user
    PAPERS_CREATED_MONTHLY_LIMIT: int = 20
    SUBMISSIONS_MADE_MONTHLY_LIMIT: int = 100
    LLM_TOKEN_BALANCE_MONTHLY_LIMIT: int = 200_000

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    @model_validator(mode="after")
    def _check_secret_key(self) -> "Settings":
        if not self.SECRET_KEY:
            if self.is_development:
                self.SECRET_KEY = _load_or_create_dev_secret()
            else:
                raise ValueError(
                    "SECRET_KEY must be set when ENVIRONMENT is not 'development'."
                )
        return self

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @property
    def reasoning_effort(self) -> str | None:
        value = self.GROQ_REASONING_EFFORT.strip().lower()
        return None if value in ("", "none", "off", "false", "0") else value

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
