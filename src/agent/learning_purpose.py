"""Supported learner intent and local prompt selection; all workflows stay shared."""
import re

from .prompts import render_prompt

PURPOSE_LABELS = {
    "certification_preparation": "Certification Preparation",
    "topic_mastery": "Topic Mastery",
    "career_development": "Career Development",
}
LEGACY_PURPOSE = "career_development"


def uses_ai_engineer_curriculum(setup: dict) -> bool:
    return setup["learning_purpose"] == "career_development" and bool(re.search(
        r"\b(?:ai|artificial intelligence|ml|machine learning)\s+(?:engineer(?:ing)?|generalist)\b",
        setup["goal"], re.IGNORECASE,
    ))


def purpose_context(setup: dict | None) -> str:
    """Compose versioned guidance from application-owned setup, when available."""
    if setup is None:
        return ""
    purpose = setup.get("learning_purpose", LEGACY_PURPOSE)
    if purpose not in PURPOSE_LABELS:
        raise ValueError("Unsupported learning purpose.")
    return render_prompt(
        "purpose.context",
        purpose=PURPOSE_LABELS[purpose],
        instructions=render_prompt("purpose." + purpose),
        goal=setup["goal"],
        hours_per_week=setup["hours_per_week"],
        max_session_minutes=setup["max_session_minutes"],
    )


def roadmap_purpose_context(setup: dict) -> str:
    """Apply roadmap session guidance without generating a weekly timetable."""
    preferred = setup.get("preferred_session_minutes")
    if "max_session_minutes" in setup:
        session_guidance = (
            f"Maximum session duration: {setup['max_session_minutes']} minutes (hard maximum).\n"
            "Suggested practice activities must fit this maximum. Split longer exercises and projects "
            "into activities within the limit; do not recommend exceeding it. This hard maximum takes "
            "precedence over any session preference. Detailed scheduling remains the Weekly Planner's responsibility."
        )
    elif preferred is not None:
        session_guidance = (
            f"Preferred session duration: {preferred} minutes.\n"
            "Treat this as soft guidance for activity suggestions, never a strict maximum. "
            "Longer practical activities may be recommended when uninterrupted work is useful; "
            "clearly indicate the longer duration and explain why."
        )
    else:
        session_guidance = "Preferred session duration: No preference. No session-duration constraint applies."
    return render_prompt(
        "roadmap.context",
        purpose=PURPOSE_LABELS[setup["learning_purpose"]],
        instructions=render_prompt("purpose." + setup["learning_purpose"]),
        goal=setup["goal"], hours_per_week=setup["hours_per_week"],
        session_guidance=session_guidance,
    )
