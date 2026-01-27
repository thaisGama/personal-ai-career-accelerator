"""Planner orchestration helpers decoupled from any UI framework."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import src.agent.react_agent as react_agent
import src.agent.weekly_planner as weekly_planner


def _ensure_data_dir(base_dir: Path) -> Path:
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _path_to_str(value: Any) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str):
        return value
    return ""


def _safe_read_text(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _normalize_result_paths(result: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(result)

    weekly_plan_path = result.get("weekly_plan_path") or result.get("plan_path")
    plan_path_str = _path_to_str(weekly_plan_path) or _path_to_str(result.get("plan_path"))
    linkedin_path_str = _path_to_str(result.get("linkedin_path"))
    learning_unit_path_str = _path_to_str(result.get("learning_unit_path"))
    memory_path_str = _path_to_str(result.get("memory_path"))

    if plan_path_str:
        normalized["plan_path"] = plan_path_str
        normalized["weekly_plan_path"] = plan_path_str
    elif "plan_path" in normalized:
        normalized["plan_path"] = _path_to_str(normalized.get("plan_path"))

    if linkedin_path_str:
        normalized["linkedin_path"] = linkedin_path_str
    if learning_unit_path_str:
        normalized["learning_unit_path"] = learning_unit_path_str
    if memory_path_str:
        normalized["memory_path"] = memory_path_str

    return normalized


def _split_non_agent_markdown(raw_md: str) -> Tuple[str, str]:
    if not raw_md:
        return "", ""
    try:
        memory_audit_block = raw_md.split("<<PLAN_MARKDOWN>>", 1)[0].strip()
        plan_text = weekly_planner.extract_between(raw_md, "<<PLAN_MARKDOWN>>", "<<END_PLAN>>")
        formatted = weekly_planner.format_weekly_plan(plan_text)
        if memory_audit_block:
            formatted = f"{memory_audit_block}\n\n{formatted}"
        plan_md, linkedin_md = weekly_planner.split_markdown_into_plan_and_linkedin(formatted)
    except Exception:
        plan_md, linkedin_md = raw_md, ""
    return plan_md, linkedin_md


def run_weekly_planner_service(
    *,
    goal: str,
    hours_per_week: float,
    max_session_minutes: int,
    preferences_text: str,
    intensity: str | None,
    background: str | None,
    roadmap_id: str | None,
    force_regenerate_roadmap: bool,
    model: str,
    use_agent_loop: bool,
    mock_actions_path: Path | None,
    enable_critic: bool,
    base_dir: Path,
) -> dict:
    """Run the weekly planner in agent or non-agent mode and return normalized outputs."""
    _ensure_data_dir(base_dir)

    if use_agent_loop:
        preferences_payload = {
            "text": preferences_text or "",
            "target_level": intensity,
            "background": background or "",
            "roadmap_id": roadmap_id or "",
            "force_regenerate_roadmap": force_regenerate_roadmap,
        }
        result = react_agent.run_weekly_planner_agent_react(
            goal=goal,
            hours_per_week=hours_per_week,
            max_session_minutes=max_session_minutes,
            preferences=preferences_payload,
            model=model,
            base_dir=base_dir,
            mock_actions_path=mock_actions_path,
            enable_critic=enable_critic,
        )
        normalized = _normalize_result_paths(result)

        plan_path = Path(normalized.get("plan_path", "")) if normalized.get("plan_path") else None
        linkedin_path = (
            Path(normalized.get("linkedin_path", "")) if normalized.get("linkedin_path") else None
        )
        plan_md = _safe_read_text(plan_path)
        linkedin_md = _safe_read_text(linkedin_path)
        return {
            "result": normalized,
            "plan_md": plan_md,
            "linkedin_md": linkedin_md,
        }

    enriched_preferences = preferences_text or ""
    if intensity or background:
        enriched_preferences = (
            f"{enriched_preferences}\n\nLearning intensity: {intensity}\nBackground: {background or 'none'}"
        ).strip()

    result = weekly_planner.generate_and_save_week(
        goal=goal,
        time_per_week_hours=hours_per_week,
        max_session_minutes=max_session_minutes,
        preferences=enriched_preferences,
        target_level=intensity,
        background=background,
        roadmap_id=roadmap_id or None,
        force_regenerate_roadmap=force_regenerate_roadmap,
        model=model,
        base_dir=base_dir,
    )
    normalized = _normalize_result_paths(result)
    raw_md = result.get("raw_markdown", "")
    plan_md, linkedin_md = _split_non_agent_markdown(raw_md)
    return {
        "result": normalized,
        "plan_md": plan_md,
        "linkedin_md": linkedin_md,
    }


__all__ = ["run_weekly_planner_service"]
