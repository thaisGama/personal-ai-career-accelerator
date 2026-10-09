"""Read-only roadmap context for the Streamlit workspace.

Historical progress has one file-level owner even when weeks belong to different
roadmaps. Only explicit week ownership is safe; never guess from topics or names.
"""

import json
from pathlib import Path


def read_progress(base_dir: Path) -> tuple[list[dict], str | None]:
    path = base_dir / "data" / "learning_progress.json"
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        weeks = data.get("weeks")
        if not isinstance(weeks, list) or any(not isinstance(w, dict) for w in weeks):
            raise ValueError("Invalid weeks")
        return weeks, None
    except (OSError, ValueError, AttributeError):
        return [], "Progress unavailable: saved progress could not be read."


def roadmap_weeks(weeks: list[dict], roadmap_id: str | None) -> list[dict]:
    return [w for w in weeks if roadmap_id and w.get("roadmap_id") == roadmap_id]


def days_in_week(week: dict) -> list[dict]:
    days = week.get("days", [])
    return [d for d in days if isinstance(d, dict)] if isinstance(days, list) else []


def day_status(day: dict) -> str:
    result = str(day.get("quiz_result") or "").upper()
    if result == "PASS":
        return "Completed"
    if result == "FAIL":
        return "Needs review"
    if "quiz_result" not in day or result or day.get("status") in {"PASSED", "NEEDS_REVIEW"}:
        return "Progress unavailable"
    return "In progress" if day.get("status") == "IN_PROGRESS" else "Not started"


def progress_summary(weeks: list[dict]) -> dict:
    entries = [(week, day) for week in weeks for day in days_in_week(week)]
    core = [d for _, d in entries if not d.get("is_review")]
    reviews = [d for _, d in entries if d.get("is_review")]
    pending = [(w, d) for w, d in entries if day_status(d) not in {"Completed", "Progress unavailable"}]
    # Prefer an existing review day over repeating its failed parent.
    review = next(((w, d) for w, d in pending if d.get("is_review")), None)
    recommended = review or (pending[0] if pending else None)
    return {
        "total": len(core),
        "completed": sum(day_status(d) == "Completed" for d in core),
        "unknown": sum(day_status(d) == "Progress unavailable" for d in core),
        "review_total": len(reviews),
        "review_completed": sum(day_status(d) == "Completed" for d in reviews),
        "recommended": recommended,
    }


def saved_resource(base_dir: Path, value: object, directory: str) -> Path | None:
    """Accept existing files only within the intended saved-resource directory."""
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    path = (path if path.is_absolute() else base_dir / path).resolve()
    if path.is_relative_to((base_dir / directory).resolve()) and path.is_file():
        return path
    return None


def learning_units(base_dir: Path, weeks: list[dict], roadmap_id: str | None) -> dict[Path, dict]:
    """Index exact saved paths; conflicting associations are omitted."""
    linked: dict[Path, list[dict]] = {}
    for week in weeks:
        owner = week.get("roadmap_id")
        if not owner:
            continue
        for day in [None, *days_in_week(week)]:
            record = day if day is not None else week
            path = saved_resource(base_dir, record.get("learning_unit_path"), "docs/learning_units")
            if path:
                linked.setdefault(path, []).append({"roadmap_id": owner, "week": week, "day": day})
    result = {}
    for path, associations in linked.items():
        if len(associations) == 1 and (not roadmap_id or associations[0]["roadmap_id"] == roadmap_id):
            result[path] = associations[0]
    if roadmap_id is None:
        for path in (base_dir / "docs" / "learning_units").glob("*.md"):
            if path.is_file():
                result.setdefault(path.resolve(), {})
    return result


def switch_roadmap(state, roadmap_id: str | None, *, existing_mode: bool = False) -> None:
    """Clear UI state before its widgets are instantiated, without disk writes."""
    if state.get("workspace_roadmap_id") != roadmap_id or state.get("workspace_existing_mode", False) != existing_mode:
        for key in list(state):
            if key in {
                "planner_result", "planner_plan_md", "planner_plan_path", "planner_linkedin_md",
                "weekly_plans_select", "learning_unit_select", "workspace_tab",
            } or key.startswith("quiz_") or key.startswith("done_"):
                state.pop(key, None)
        state["workspace_roadmap_id"] = roadmap_id
        state["workspace_existing_mode"] = existing_mode
    state["active_roadmap_id"] = roadmap_id or ""
    if roadmap_id:
        state["quiz_roadmap_id"] = roadmap_id
