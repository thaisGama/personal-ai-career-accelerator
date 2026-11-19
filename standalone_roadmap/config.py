"""Server-owned standalone settings, read from the environment per submission."""

from dataclasses import dataclass
import os
from typing import Mapping

ROADMAP_MODEL = "gpt-6-luna"
MAX_GOAL_CHARACTERS = 2_000
MAX_BACKGROUND_CHARACTERS = 6_000
ROADMAP_TIMEOUT_SECONDS = 120.0
ROADMAP_MAX_TOKENS = 8_000


class ConfigurationError(ValueError):
    """Invalid server configuration; never includes supplied values or secrets."""


@dataclass(frozen=True)
class RoadmapConfig:
    environment: str
    generation_enabled: bool
    daily_limit: int | None  # None means unlimited (development only).


def load_config(environ: Mapping[str, str] | None = None) -> RoadmapConfig:
    """Fail closed on invalid settings; missing environment uses beta safeguards."""
    env = os.environ if environ is None else environ
    environment = env.get("ROADMAP_ENVIRONMENT", "beta").strip().lower()
    if environment not in ("development", "beta", "production"):
        raise ConfigurationError("ROADMAP_ENVIRONMENT must be development, beta, or production.")

    enabled = env.get("ROADMAP_GENERATION_ENABLED", "true").strip().lower()
    if enabled not in ("true", "false"):
        raise ConfigurationError("ROADMAP_GENERATION_ENABLED must be true or false.")

    default_limit = "0" if environment == "development" else "10"
    raw_limit = env.get("ROADMAP_DAILY_LIMIT", default_limit).strip()
    if not raw_limit.isascii() or not raw_limit.isdecimal():
        raise ConfigurationError("ROADMAP_DAILY_LIMIT must be a non-negative integer.")
    try:
        daily_limit = int(raw_limit)
    except ValueError:
        raise ConfigurationError("ROADMAP_DAILY_LIMIT must be a non-negative integer.") from None
    if environment != "development" and not 1 <= daily_limit <= 10:
        raise ConfigurationError("ROADMAP_DAILY_LIMIT must be between 1 and 10 in beta/production.")
    if enabled == "true" and not env.get("OPENAI_API_KEY", "").strip():
        raise ConfigurationError("OPENAI_API_KEY is required when generation is enabled.")
    return RoadmapConfig(environment, enabled == "true", daily_limit or None)
