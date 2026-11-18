"""One roadmap request using shared helpers, without application persistence."""

import logging
import math
from time import perf_counter

from openai import APITimeoutError

from src.agent.learner_setup import make_roadmap_learner_setup
from src.agent.tools import (
    _render_roadmap_markdown,
    build_roadmap_prompt,
    parse_roadmap_output,
)
from src.agent.weekly_planner import call_llm
from .admission import RoadmapUnavailableError, admission_controller
from .config import (
    ConfigurationError,
    MAX_BACKGROUND_CHARACTERS,
    MAX_GOAL_CHARACTERS,
    ROADMAP_MAX_TOKENS,
    ROADMAP_MODEL,
    ROADMAP_TIMEOUT_SECONDS,
    load_config,
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _log_outcome(outcome: str, category: str, started: float, metadata: dict) -> None:
    """Diagnostics are best effort and contain only server-owned fields/counts."""
    try:
        usage = metadata.get("usage") or {}
        # Whitelist numeric counts; never interpolate provider/user text.
        counts = {key: value if type(value := usage.get(key)) is int and value >= 0 else None
                  for key in ("prompt_tokens", "completion_tokens")}
        logger.info(
            "roadmap_generation outcome=%s category=%s duration_seconds=%.3f "
            "model=%s input_tokens=%s output_tokens=%s",
            outcome, category, perf_counter() - started, ROADMAP_MODEL,
            counts["prompt_tokens"], counts["completion_tokens"],
        )
    except Exception:
        # A broken logging handler must never change results or quota accounting.
        pass


class RoadmapGenerationError(Exception):
    """A generation failure whose message is safe to display to the learner."""


def generate_roadmap(*, goal: str, background: str = "",
                     learning_purpose: str = "career_development",
                     hours_per_week: float = 2.0,
                     learning_intensity: str = "medium",
                     preferred_session_minutes: int | None = None,
                     timeout_seconds: float = ROADMAP_TIMEOUT_SECONDS) -> str:
    """Validate inputs, make one request, and return validated roadmap Markdown.

    Invalid inputs raise ValueError before any request. API and output failures
    raise RoadmapGenerationError without exposing raw responses or API details.
    Admission/configuration refusals raise RoadmapUnavailableError without using quota.
    Server callers may override timeout_seconds with a positive finite duration.
    """
    setup = make_roadmap_learner_setup(
        goal=goal, background=background, preferences="",
        learning_purpose=learning_purpose, hours_per_week=hours_per_week,
        preferred_session_minutes=preferred_session_minutes,
        learning_intensity=learning_intensity,
    )
    for field, label, limit in (
        ("goal", "Learning goal", MAX_GOAL_CHARACTERS),
        ("background", "Background", MAX_BACKGROUND_CHARACTERS),
    ):
        if len(setup[field]) > limit:
            raise ValueError(f"{label} must be {limit:,} characters or fewer. Please shorten it.")
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("Roadmap timeout must be a positive, finite number of seconds.")
    try:
        config = load_config()
    except ConfigurationError:
        raise RoadmapUnavailableError(
            "Roadmap generation is unavailable. Please contact the app owner."
        ) from None
    prompt = build_roadmap_prompt(
        setup["goal"], setup["learning_intensity"], setup["background"], setup,
    )
    with admission_controller.admit(config):
        started = perf_counter()
        metadata: dict = {}
        outcome, category = "failure", "internal_error"
        try:
            try:
                raw = call_llm(
                    system_prompt=prompt["system"], user_prompt=prompt["user"],
                    model=ROADMAP_MODEL, max_retries=0, timeout=timeout_seconds,
                    max_tokens=ROADMAP_MAX_TOKENS, response_metadata=metadata, log_usage=False,
                )
            except Exception as exc:
                category = ("api_timeout" if isinstance(exc, APITimeoutError)
                            or isinstance(exc.__cause__, APITimeoutError) else "api_failure")
                raise RoadmapGenerationError(
                    "Could not generate a roadmap. Check the server API configuration "
                    "and connection, then submit again."
                ) from None

            try:
                parsed = parse_roadmap_output(raw, setup)
                if parsed.get("error"):
                    raise ValueError("Invalid roadmap output")
                markdown = _render_roadmap_markdown(parsed["roadmap"])
            except (TypeError, ValueError, KeyError, AttributeError):
                category = "invalid_output"
                raise RoadmapGenerationError(
                    "The model returned an invalid roadmap. Please submit again."
                ) from None
            outcome, category = "success", "none"
            return markdown
        finally:
            _log_outcome(outcome, category, started, metadata)
