"""One roadmap request using shared helpers, without application persistence."""

import math

from src.agent.learner_setup import make_learner_setup, validate_learner_setup
from src.agent.tools import (
    _render_roadmap_markdown,
    build_roadmap_prompt,
    parse_roadmap_output,
)
from src.agent.weekly_planner import call_llm

# Server-owned configuration; these values are not supplied by the browser.
ROADMAP_MODEL = "gpt-6-luna"
MAX_SESSION_MINUTES = 30
MAX_GOAL_CHARACTERS = 2_000
MAX_BACKGROUND_CHARACTERS = 6_000
ROADMAP_TIMEOUT_SECONDS = 120.0
ROADMAP_MAX_TOKENS = 8_000


class RoadmapGenerationError(Exception):
    """A generation failure whose message is safe to display to the learner."""


def generate_roadmap(*, goal: str, background: str = "",
                     learning_purpose: str = "career_development",
                     hours_per_week: float = 2.0,
                     learning_intensity: str = "medium",
                     timeout_seconds: float = ROADMAP_TIMEOUT_SECONDS) -> str:
    """Validate inputs, make one request, and return validated roadmap Markdown.

    Invalid inputs raise ValueError before any request. API and output failures
    raise RoadmapGenerationError without exposing raw responses or API details.
    Server callers may override timeout_seconds with a positive finite duration.
    """
    setup = validate_learner_setup(make_learner_setup(
        goal=goal, background=background, preferences="",
        learning_purpose=learning_purpose, hours_per_week=hours_per_week,
        max_session_minutes=MAX_SESSION_MINUTES,
        learning_intensity=learning_intensity,
    ))
    for field, label, limit in (
        ("goal", "Learning goal", MAX_GOAL_CHARACTERS),
        ("background", "Background", MAX_BACKGROUND_CHARACTERS),
    ):
        if len(setup[field]) > limit:
            raise ValueError(f"{label} must be {limit:,} characters or fewer. Please shorten it.")
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("Roadmap timeout must be a positive, finite number of seconds.")
    prompt = build_roadmap_prompt(
        setup["goal"], setup["learning_intensity"], setup["background"], setup,
    )
    try:
        raw = call_llm(
            system_prompt=prompt["system"], user_prompt=prompt["user"],
            model=ROADMAP_MODEL, max_retries=0, timeout=timeout_seconds,
            max_tokens=ROADMAP_MAX_TOKENS,
        )
    except Exception:
        raise RoadmapGenerationError(
            "Could not generate a roadmap. Check the server API configuration "
            "and connection, then submit again."
        ) from None

    try:
        parsed = parse_roadmap_output(raw, setup)
        if parsed.get("error"):
            raise ValueError("Invalid roadmap output")
        return _render_roadmap_markdown(parsed["roadmap"])
    except (TypeError, ValueError, KeyError, AttributeError):
        raise RoadmapGenerationError(
            "The model returned an invalid roadmap. Please submit again."
        ) from None
