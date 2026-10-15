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


def resolve_quiz_day(weeks: list[dict], roadmap_id: str | None, selected_day: dict | None = None) -> tuple[dict | None, str | None]:
    """Prefer explicit identity over the recommendation; never guess a day."""
    if not roadmap_id:
        return None, None
    selected_weeks = roadmap_weeks(weeks, roadmap_id)
    if selected_day is not None:
        matches = [(w, d) for w in selected_weeks for d in days_in_week(w)
                   if selected_day.get("roadmap_id") == roadmap_id
                   and w.get("week_id") == selected_day.get("week_id")
                   and d.get("day_id") == selected_day.get("day_id")]
        if len(matches) != 1:
            return None, "The selected learning day is unavailable or ambiguous. Select a linked day in the Learning Library."
        week, day = matches[0]
    else:
        recommended = progress_summary(selected_weeks)["recommended"]
        if not recommended:
            return None, None
        week, day = recommended
    if (not week.get("week_id") or week.get("week_number_global") is None
            or not day.get("day_id") or day.get("day_number") is None
            or not str(day.get("topic") or "").strip()
            or sum(d.get("day_id") == day.get("day_id") for w in weeks for d in days_in_week(w)) != 1):
        return None, "The selected learning day has incomplete or ambiguous metadata. A day-linked quiz cannot be generated."
    return {"roadmap_id": roadmap_id, "week": week, "day": day}, None


def quiz_day_identity(context: dict) -> dict:
    return {"roadmap_id": context["roadmap_id"], "week_id": context["week"].get("week_id"),
            "day_id": context["day"].get("day_id")}


def preserve_quiz_draft(state) -> None:
    """Keep unsent quiz/answers in session when navigation invalidates them."""
    answers = {k: state[k] for k in list(state) if k.startswith("quiz_answer_") or k == "quiz_answers_fallback"}
    if state.get("quiz_markdown") and (not state.get("quiz_eval") or answers != state.get("quiz_submitted_answers", {})):
        draft = {k: state[k] for k in list(state) if k.startswith("quiz_")}
        state.setdefault("saved_quiz_drafts", []).append(draft)
        state["quiz_draft_notice"] = "Quiz context changed. The previous quiz and unsent answers were preserved below and will not be submitted for the new day."


def sync_quiz_context(state, context: dict | None, error: str | None = None) -> None:
    key = tuple(quiz_day_identity(context).values()) if context else ("invalid" if error else "standalone",)
    if state.get("quiz_context_key") != key:
        preserve_quiz_draft(state)
        for name in list(state):
            if name in {"quiz_markdown", "quiz_path", "quiz_binding", "quiz_generation_topic", "quiz_eval",
                        "quiz_eval_block", "quiz_eval_score", "quiz_eval_mastery", "quiz_eval_decision",
                        "quiz_answers_fallback", "quiz_unlocked", "quiz_task_update", "quiz_propose_done",
                        "quiz_task_ids", "quiz_selected_tasks", "quiz_task_statuses", "quiz_submitted_answers"} or name.startswith("quiz_answer_") or name.startswith("done_"):
                state.pop(name, None)
        state["quiz_context_key"] = key


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
        preserve_quiz_draft(state)
        notice = state.get("quiz_draft_notice")
        for key in list(state):
            if key in {
                "planner_result", "planner_plan_md", "planner_plan_path", "planner_linkedin_md",
                "weekly_plans_select", "learning_unit_select", "workspace_tab", "selected_learning_day",
            } or key.startswith("quiz_") or key.startswith("done_"):
                state.pop(key, None)
        state["workspace_roadmap_id"] = roadmap_id
        state["workspace_existing_mode"] = existing_mode
        if notice:
            state["quiz_draft_notice"] = notice
    state["active_roadmap_id"] = roadmap_id or ""
    if roadmap_id:
        state["quiz_roadmap_id"] = roadmap_id
