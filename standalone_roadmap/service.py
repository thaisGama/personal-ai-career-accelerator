"""One roadmap request using shared helpers, without application persistence."""

from src.agent.learner_setup import make_learner_setup, validate_learner_setup
from src.agent.tools import (
    _render_roadmap_markdown,
    build_roadmap_prompt,
    parse_roadmap_output,
)
from src.agent.weekly_planner import call_llm

# Server-owned configuration; neither value is supplied by the browser.
ROADMAP_MODEL = "gpt-6-luna"
MAX_SESSION_MINUTES = 30


class RoadmapGenerationError(Exception):
    """A generation failure whose message is safe to display to the learner."""


def generate_roadmap(*, goal: str, background: str = "",
                     learning_purpose: str = "career_development",
                     hours_per_week: float = 2.0,
                     learning_intensity: str = "medium") -> str:
    """Validate inputs, make one request, and return validated roadmap Markdown.

    Invalid inputs raise ValueError before any request. API and output failures
    raise RoadmapGenerationError without exposing raw responses or API details.
    """
    setup = validate_learner_setup(make_learner_setup(
        goal=goal, background=background, preferences="",
        learning_purpose=learning_purpose, hours_per_week=hours_per_week,
        max_session_minutes=MAX_SESSION_MINUTES,
        learning_intensity=learning_intensity,
    ))
    prompt = build_roadmap_prompt(
        setup["goal"], setup["learning_intensity"], setup["background"], setup,
    )
    try:
        raw = call_llm(
            system_prompt=prompt["system"], user_prompt=prompt["user"],
            model=ROADMAP_MODEL, max_retries=0,
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
