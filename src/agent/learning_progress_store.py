"""JSON-backed learning progression helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .task_store import (
    _extract_micro_task_lines,
    _extract_roadmap_tags,
    _parse_task_line,
    _strip_roadmap_tags,
)


def resolve_learning_progress_path(base_dir: Path) -> Path:
    return Path(base_dir) / "data" / "learning_progress.json"


def empty_learning_progress(roadmap_id: str = "") -> Dict[str, Any]:
    return {
        "roadmap_id": roadmap_id,
        "status": "TODO",
        "weeks": [],
    }


def ensure_learning_progress_file(path: Path, roadmap_id: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_learning_progress(path, empty_learning_progress(roadmap_id=roadmap_id))


def load_learning_progress(path: Path, roadmap_id: str = "") -> Dict[str, Any]:
    ensure_learning_progress_file(path, roadmap_id=roadmap_id)
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("roadmap_id", roadmap_id)
    data.setdefault("status", "TODO")
    data.setdefault("weeks", [])
    return data


def save_learning_progress(path: Path, progress: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(progress, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def find_week_and_day(progress: Dict[str, Any], day_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    for week in progress.get("weeks", []):
        for day in week.get("days", []):
            if day.get("day_id") == day_id:
                return week, day
    raise KeyError(f"Day not found: {day_id}")


def update_day_learning_unit_path(
    path: Path,
    day_id: str,
    learning_unit_path: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    progress = load_learning_progress(path)
    week, day = find_week_and_day(progress, day_id)
    day["learning_unit_path"] = learning_unit_path
    save_learning_progress(path, progress)
    return progress, week, day


def update_day_quiz_path(
    path: Path,
    day_id: str,
    quiz_path: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    progress = load_learning_progress(path)
    week, day = find_week_and_day(progress, day_id)
    day["quiz_path"] = quiz_path
    save_learning_progress(path, progress)
    return progress, week, day


def update_day_validation_result(
    path: Path,
    day_id: str,
    quiz_result: str,
    reflection: str = "",
    review_reason: str = "",
    completed_at: str | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    normalized = quiz_result.strip().upper()
    if normalized not in {"PASS", "FAIL"}:
        raise ValueError(f"Unsupported quiz result: {quiz_result}")

    progress = load_learning_progress(path)
    week, day = find_week_and_day(progress, day_id)
    day["quiz_result"] = normalized
    day["status"] = "PASSED" if normalized == "PASS" else "NEEDS_REVIEW"
    day["completed_at"] = completed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    day["reflection"] = reflection
    day["review_reason"] = "" if normalized == "PASS" else review_reason
    recompute_progress_statuses(progress)
    save_learning_progress(path, progress)
    return progress, week, day


def _status_from_children(statuses: List[str]) -> str:
    normalized = [str(status or "TODO").upper() for status in statuses]
    if not normalized:
        return "TODO"
    if all(status == "PASSED" for status in normalized):
        return "PASSED"
    if any(status == "NEEDS_REVIEW" for status in normalized):
        return "NEEDS_REVIEW"
    if any(status in {"IN_PROGRESS", "PASSED"} for status in normalized):
        return "IN_PROGRESS"
    return "TODO"


def compute_week_status(week: Dict[str, Any]) -> str:
    return _status_from_children([str(day.get("status") or "TODO") for day in week.get("days", [])])


def recompute_progress_statuses(progress: Dict[str, Any]) -> Dict[str, Any]:
    weeks = progress.setdefault("weeks", [])
    for week in weeks:
        week["status"] = compute_week_status(week)

    milestone_entries: List[Dict[str, Any]] = []
    milestone_order: List[str] = []
    milestone_weeks: Dict[str, List[Dict[str, Any]]] = {}
    milestone_phase: Dict[str, str] = {}
    for week in weeks:
        milestone_id = str(week.get("milestone_id") or "")
        if not milestone_id:
            continue
        if milestone_id not in milestone_weeks:
            milestone_order.append(milestone_id)
            milestone_weeks[milestone_id] = []
            milestone_phase[milestone_id] = str(week.get("phase_id") or "")
        milestone_weeks[milestone_id].append(week)

    for milestone_id in milestone_order:
        grouped_weeks = milestone_weeks[milestone_id]
        milestone_entries.append(
            {
                "milestone_id": milestone_id,
                "phase_id": milestone_phase.get(milestone_id, ""),
                "status": _status_from_children([str(week.get("status") or "TODO") for week in grouped_weeks]),
            }
        )
    progress["milestones"] = milestone_entries

    phase_entries: List[Dict[str, Any]] = []
    phase_order: List[str] = []
    phase_milestones: Dict[str, List[Dict[str, Any]]] = {}
    for milestone in milestone_entries:
        phase_id = str(milestone.get("phase_id") or "")
        if not phase_id:
            continue
        if phase_id not in phase_milestones:
            phase_order.append(phase_id)
            phase_milestones[phase_id] = []
        phase_milestones[phase_id].append(milestone)

    for phase_id in phase_order:
        grouped_milestones = phase_milestones[phase_id]
        phase_entries.append(
            {
                "phase_id": phase_id,
                "status": _status_from_children(
                    [str(milestone.get("status") or "TODO") for milestone in grouped_milestones]
                ),
            }
        )
    progress["phases"] = phase_entries

    if phase_entries:
        progress["status"] = _status_from_children([str(phase.get("status") or "TODO") for phase in phase_entries])
    elif milestone_entries:
        progress["status"] = _status_from_children(
            [str(milestone.get("status") or "TODO") for milestone in milestone_entries]
        )
    else:
        progress["status"] = _status_from_children([str(week.get("status") or "TODO") for week in weeks])
    return progress


def _next_week_id(progress: Dict[str, Any]) -> str:
    return f"week_{len(progress.get('weeks', [])) + 1:03d}"


def _next_day_start(progress: Dict[str, Any]) -> int:
    max_day = 0
    for week in progress.get("weeks", []):
        for day in week.get("days", []):
            match = re.fullmatch(r"day_(\d+)", str(day.get("day_id", "")))
            if match:
                max_day = max(max_day, int(match.group(1)))
    return max_day + 1


def _extract_week_title(plan_md: str, fallback_week_number: int) -> str:
    for line in plan_md.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped.lower().startswith("week "):
            return stripped
    return f"Week {fallback_week_number} Learning Plan"


def _parse_day_number(line: str, fallback: int) -> int:
    clean = line.lstrip("-• ").replace("**", "").strip()
    match = re.search(r"\bday\s*(\d+)\b", clean, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return fallback


def parse_days_from_plan(plan_md: str) -> List[Dict[str, Any]]:
    days: List[Dict[str, Any]] = []
    for index, line in enumerate(_extract_micro_task_lines(plan_md), start=1):
        phase_id, milestone_id = _extract_roadmap_tags(line)
        cleaned_line = _strip_roadmap_tags(line)
        topic, estimated_minutes, _priority = _parse_task_line(cleaned_line, default_priority=3)
        if not topic:
            continue
        days.append(
            {
                "day_number": _parse_day_number(cleaned_line, fallback=index),
                "topic": topic,
                "estimated_minutes": estimated_minutes or 0,
                "phase_id": phase_id or "",
                "milestone_id": milestone_id or "",
            }
        )
    return days


def append_week_from_plan(
    path: Path,
    plan_md: str,
    roadmap_id: str = "",
    phase_id: str = "",
    milestone_id: str = "",
    week_number_global: int | None = None,
    title: str | None = None,
    goal: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    progress = load_learning_progress(path, roadmap_id=roadmap_id)
    existing_roadmap_id = str(progress.get("roadmap_id") or "")
    if roadmap_id and not existing_roadmap_id:
        progress["roadmap_id"] = roadmap_id

    weeks = progress.setdefault("weeks", [])
    week_number = week_number_global or len(weeks) + 1
    next_day = _next_day_start(progress)
    parsed_days = parse_days_from_plan(plan_md)
    inferred_phase_id = phase_id or next((day["phase_id"] for day in parsed_days if day["phase_id"]), "")
    inferred_milestone_id = milestone_id or next(
        (day["milestone_id"] for day in parsed_days if day["milestone_id"]), ""
    )
    week_number_in_milestone = (
        sum(1 for week in weeks if str(week.get("milestone_id") or "") == inferred_milestone_id) + 1
        if inferred_milestone_id
        else week_number
    )
    estimated_minutes = sum(int(day.get("estimated_minutes") or 0) for day in parsed_days)
    days = []
    for offset, day in enumerate(parsed_days):
        days.append(
            {
                "day_id": f"day_{next_day + offset:03d}",
                "day_number": day["day_number"],
                "topic": day["topic"],
                "estimated_minutes": day["estimated_minutes"],
                "learning_unit_path": "",
                "quiz_path": "",
                "status": "TODO",
                "quiz_result": "",
                "completed_at": "",
                "reflection": "",
                "review_reason": "",
                "is_review": False,
                "review_of_day_id": "",
            }
        )

    week = {
        "week_id": _next_week_id(progress),
        "phase_id": inferred_phase_id,
        "milestone_id": inferred_milestone_id,
        "week_number_global": week_number,
        "week_number_in_milestone": week_number_in_milestone,
        "title": title or _extract_week_title(plan_md, week_number),
        "goal": goal,
        "estimated_minutes": estimated_minutes,
        "status": "TODO",
        "days": days,
    }
    weeks.append(week)
    save_learning_progress(path, progress)
    return progress, week


__all__ = [
    "append_week_from_plan",
    "compute_week_status",
    "empty_learning_progress",
    "ensure_learning_progress_file",
    "find_week_and_day",
    "load_learning_progress",
    "parse_days_from_plan",
    "recompute_progress_statuses",
    "resolve_learning_progress_path",
    "save_learning_progress",
    "update_day_learning_unit_path",
    "update_day_quiz_path",
    "update_day_validation_result",
]
