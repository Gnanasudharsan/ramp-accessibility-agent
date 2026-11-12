"""Runtime configuration, read from environment variables (prefix ``RAMP_``) and ``.env``."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunables in one place so behaviour is reproducible from the environment."""

    model_config = SettingsConfigDict(env_prefix="RAMP_", env_file=".env", extra="ignore")

    # Crawling etiquette (see CLAUDE.md, section 3).
    user_agent: str = (
        "RampA11yBot/0.1 (+https://github.com/Gnanasudharsan/ramp-accessibility-agent)"
    )
    max_pages: int = Field(default=10, ge=1, le=200)
    max_depth: int = Field(default=2, ge=0, le=5)
    min_seconds_between_requests: float = Field(default=1.0, ge=1.0)

    # Infrastructure.
    redis_url: str = "redis://localhost:6379/1"

    # Models (LiteLLM model strings, e.g. "groq/<model>" or "gemini/<model>"). See ADR 0005.
    vision_model: str = "groq/qwen/qwen3.8-27b"
    text_model: str = "groq/openai/gpt-oss-120b"
    llm_cache_dir: str = ".ramp/llm-cache"
    llm_max_retries: int = Field(default=2, ge=0, le=5)  # schema-violation retries
    vision_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    max_images_per_page: int = Field(default=15, ge=0, le=100)
    max_fixes_per_audit: int = Field(default=40, ge=0, le=500)
    # Optional list prices (USD per 1M tokens) for cost reporting; 0 = unknown / free tier.
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0
    demo_mode: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (cached; call ``get_settings.cache_clear()`` in tests)."""
    return Settings()
