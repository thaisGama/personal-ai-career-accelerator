"""Application-owned setup embedded in each roadmap; no legacy defaults."""
import json
import math
from pathlib import Path


def validate_learner_setup(setup: object) -> dict:
    if not isinstance(setup, dict):
        raise ValueError("Roadmap learner_setup must be a complete object.")
    for field in ("goal", "background", "preferences"):
        if not isinstance(setup.get(field), str):
            raise ValueError(f"Roadmap learner_setup.{field} must be a string.")
    if not setup["goal"].strip():
        raise ValueError("Roadmap learner_setup.goal must not be empty.")
    hours = setup.get("hours_per_week")
    if type(hours) not in (int, float) or not math.isfinite(hours) or not 0.5 <= hours <= 10 or hours * 2 != int(hours * 2):
        raise ValueError("Roadmap learner_setup.hours_per_week must be 0.5–10 in half-hour steps.")
    minutes = setup.get("max_session_minutes")
    if type(minutes) is not int or minutes not in (10, 15, 20, 30, 45, 60):
        raise ValueError("Roadmap learner_setup.max_session_minutes must be 10, 15, 20, 30, 45, or 60.")
    if setup.get("learning_intensity") not in ("light", "medium", "hardcore"):
        raise ValueError("Roadmap learner_setup.learning_intensity must be light, medium, or hardcore.")
    return dict(setup)


def make_learner_setup(*, goal, background, preferences, hours_per_week, max_session_minutes, learning_intensity):
    return validate_learner_setup(dict(
        goal=goal, background=background, preferences=preferences,
        hours_per_week=hours_per_week, max_session_minutes=max_session_minutes,
        learning_intensity=learning_intensity,
    ))


def load_learner_setup(base_dir: Path, roadmap_id: str) -> dict:
    # IDs are the stable filename slug used by the existing roadmap store.
    if not roadmap_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in roadmap_id):
        raise ValueError("Invalid saved roadmap identifier.")
    path = Path(base_dir) / "roadmaps" / f"{roadmap_id}_roadmap.json"
    try:
        roadmap = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not load selected roadmap {roadmap_id}: {exc}") from exc
    if not isinstance(roadmap, dict):
        raise ValueError("Roadmap JSON must be an object with learner_setup.")
    return validate_learner_setup(roadmap.get("learner_setup"))
