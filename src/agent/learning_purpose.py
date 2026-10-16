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
