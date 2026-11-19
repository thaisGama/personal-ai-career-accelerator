"""Environment validation without credentials or network access."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone_roadmap.config import ConfigurationError, load_config


@pytest.mark.parametrize("environment,limit", [
    ("development", None), ("beta", 10), ("production", 10),
])
def test_environment_defaults(environment, limit):
    config = load_config({"ROADMAP_ENVIRONMENT": environment, "OPENAI_API_KEY": "fake-key"})
    assert config.environment == environment
    assert config.daily_limit == limit
    assert config.generation_enabled


def test_missing_environment_uses_beta_safeguards():
    config = load_config({"OPENAI_API_KEY": "fake-key"})
    assert config.environment == "beta" and config.daily_limit == 10


@pytest.mark.parametrize("settings", [
    {}, {"OPENAI_API_KEY": " "}, {"ROADMAP_ENVIRONMENT": ""},
    {"ROADMAP_ENVIRONMENT": "dev"}, {"ROADMAP_GENERATION_ENABLED": "1"},
    {"ROADMAP_GENERATION_ENABLED": ""}, {"ROADMAP_DAILY_LIMIT": ""},
    {"ROADMAP_DAILY_LIMIT": "-1"}, {"ROADMAP_DAILY_LIMIT": "1.5"},
    {"ROADMAP_DAILY_LIMIT": "0"}, {"ROADMAP_DAILY_LIMIT": "11"},
    {"ROADMAP_DAILY_LIMIT": "unlimited"},
])
def test_invalid_or_missing_settings_fail_closed(settings):
    env = {"OPENAI_API_KEY": "fake-key", **settings}
    if not settings:
        env.pop("OPENAI_API_KEY")
    with pytest.raises(ConfigurationError):
        load_config(env)


def test_disabled_generation_needs_no_api_key():
    assert not load_config({"ROADMAP_GENERATION_ENABLED": "false"}).generation_enabled


@pytest.mark.parametrize("environment,limit,expected", [
    ("development", "0", None), ("development", "20", 20),
    ("beta", "1", 1), ("production", "5", 5),
])
def test_explicit_daily_limits(environment, limit, expected):
    config = load_config({
        "OPENAI_API_KEY": "fake-key", "ROADMAP_ENVIRONMENT": environment,
        "ROADMAP_DAILY_LIMIT": limit,
    })
    assert config.daily_limit == expected
