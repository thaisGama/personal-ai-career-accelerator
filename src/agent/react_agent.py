"""Minimal ReAct-style agent runner for weekly planning."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .critic import run_plan_critic
from .learning_progress_store import append_week_from_plan, resolve_learning_progress_path
from .memory.vector_store import LocalVectorStore
from .tools import (
    tool_decide_next_task,
    tool_generate_learning_roadmap,
    tool_generate_weekly_plan,
    tool_load_learning_roadmap,
    tool_retrieve_memory,
    tool_save_outputs,
    tool_summarize_task_progress,
    tool_upsert_tasks_from_plan,
)
from .weekly_planner import DEFAULT_MODEL, call_llm

TOOL_DISPATCH = {
    "retrieve_memory": tool_retrieve_memory,
    "summarize_task_progress": tool_summarize_task_progress,
    "load_learning_roadmap": tool_load_learning_roadmap,
    "generate_learning_roadmap": tool_generate_learning_roadmap,
    "generate_weekly_plan": tool_generate_weekly_plan,
    "upsert_tasks_from_plan": tool_upsert_tasks_from_plan,
    "save_outputs": tool_save_outputs,
    "decide_next_task": tool_decide_next_task,
}


@dataclass
class AgentStepTrace:
    """Trace entry for one agent step."""

    step_name: str
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output_summary: str
    tool_output_full: Dict[str, Any]
    ts: str


def _summarize_output(step_name: str, output: Dict[str, Any]) -> str:
    if step_name in {"retrieve_memory", "tool_retrieve_memory"}:
        return f"memory_used={output.get('audit', {}).get('memory_used')} hits={len(output.get('memory_hits', []))}"
    if step_name in {"summarize_task_progress", "tool_summarize_task_progress"}:
        counts = output.get("counts_by_status", {})
        return f"tasks={sum(counts.values())} needs_review={counts.get('NEEDS_REVIEW', 0)}"
    if step_name in {"generate_plan", "generate_weekly_plan", "tool_generate_weekly_plan"}:
        plan_len = len(output.get("weekly_plan_md", ""))
        return f"generated plan chars={plan_len}"
    if step_name in {"load_learning_roadmap", "tool_load_learning_roadmap"}:
        return f"exists={output.get('exists')}"
    if step_name in {"generate_learning_roadmap", "tool_generate_learning_roadmap"}:
        error = output.get("error")
        if error:
            return f"error={error}"
        return f"saved={output.get('path')}"
    if step_name in {"upsert_tasks_from_plan", "tool_upsert_tasks_from_plan"}:
        return f"created={output.get('created_count')} updated={output.get('updated_count')}"
    if step_name in {"save_outputs", "tool_save_outputs"}:
        return f"saved plan={output.get('weekly_plan_path')} linkedin={output.get('linkedin_path')}"
    if step_name in {"decide_next_task", "tool_decide_next_task"}:
        return f"next_task={output.get('next_task')}"
    if step_name in {"critic_plan_review", "tool_critic_plan_review"}:
        violations = output.get("violations", [])
        patches = output.get("patch_list", [])
        return f"status={output.get('status')} violations={len(violations)} patches={len(patches)}"
    if step_name == "controller":
        return f"action={output.get('action')}"
    return "ok"


def _trace_to_dict(trace: AgentStepTrace) -> Dict[str, Any]:
    data = asdict(trace)
    return data


def run_weekly_planner_agent_fixed(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int = 30,
    preferences: str | None = None,
    model: str = DEFAULT_MODEL,
    base_dir: Path | str = ".",
    enable_critic: bool = False,
) -> Dict[str, Any]:
    """Run the multi-step weekly planner agent and persist a trace JSON file."""
    base_path = Path(base_dir)
    preferences_payload = {"text": preferences or ""}
    traces: List[AgentStepTrace] = []

    def record(step_name: str, tool_name: str, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> None:
        traces.append(
            AgentStepTrace(
                step_name=step_name,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output_summary=_summarize_output(step_name, tool_output),
                tool_output_full=tool_output,
                ts=datetime.now().isoformat(),
            )
        )

    goal_payload = {
        "goal": goal,
        "time_per_week_hours": time_per_week_hours,
        "max_session_minutes": max_session_minutes,
        "preferences": preferences_payload,
    }
    record(step_name="understand_goal", tool_name="internal", tool_input=goal_payload, tool_output=goal_payload)

    store = LocalVectorStore(path=base_path / "data" / "memory_vectors.json")
    tasks_path = base_path / "data" / "tasks.csv"
    memory_output = tool_retrieve_memory(goal=goal, preferences=preferences_payload, store=store, k=8)
    record(
        step_name="retrieve_memory",
        tool_name="tool_retrieve_memory",
        tool_input={"goal": goal, "preferences": preferences_payload, "k": 8},
        tool_output=memory_output,
    )

    tasks_summary = tool_summarize_task_progress(tasks_path=tasks_path)
    record(
        step_name="summarize_task_progress",
        tool_name="tool_summarize_task_progress",
        tool_input={"tasks_path": tasks_path.as_posix()},
        tool_output=tasks_summary,
    )

    plan_output = tool_generate_weekly_plan(
        goal=goal,
        hours_per_week=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences_payload,
        memory_context=memory_output.get("memory_context", ""),
        audit=memory_output.get("audit", {}),
        model=model,
        base_dir=base_path,
        task_progress=tasks_summary,
    )
    record(
        step_name="generate_plan",
        tool_name="tool_generate_weekly_plan",
        tool_input={
            "goal": goal,
            "hours_per_week": time_per_week_hours,
            "max_session_minutes": max_session_minutes,
            "preferences": preferences_payload,
            "model": model,
        },
        tool_output=plan_output,
    )

    critic_report = None
    if enable_critic:
        misbehaviors_path = base_path / "docs" / "misbehaviors.md"
        misbehaviors_chars = (
            len(misbehaviors_path.read_text(encoding="utf-8")) if misbehaviors_path.exists() else 0
        )
        critic_report = run_plan_critic(
            weekly_plan_md=plan_output.get("weekly_plan_md", ""),
            base_dir=base_path,
            model=model,
        )
        record(
            step_name="critic_plan_review",
            tool_name="tool_critic_plan_review",
            tool_input={
                "plan_chars": len(plan_output.get("weekly_plan_md", "")),
                "misbehaviors_chars": misbehaviors_chars,
            },
            tool_output=critic_report,
        )

    upsert_output = tool_upsert_tasks_from_plan(
        plan_md=plan_output.get("weekly_plan_md", ""),
        tasks_path=tasks_path,
        source_week=date.today().isoformat(),
        default_priority=3,
    )
    record(
        step_name="upsert_tasks_from_plan",
        tool_name="tool_upsert_tasks_from_plan",
        tool_input={"tasks_path": tasks_path.as_posix()},
        tool_output=upsert_output,
    )

    save_output = tool_save_outputs(
        base_dir=base_path,
        weekly_plan_md=plan_output.get("weekly_plan_md", ""),
        linkedin_post_md=plan_output.get("linkedin_post_md", ""),
        memory_snippet=plan_output.get("memory_snippet", ""),
        learning_unit_md=plan_output.get("learning_unit_md", ""),
        learning_unit_slug_source=goal,
    )
    record(
        step_name="save_outputs",
        tool_name="tool_save_outputs",
        tool_input={
            "base_dir": base_path.as_posix(),
            "weekly_plan_chars": len(plan_output.get("weekly_plan_md", "")),
            "linkedin_chars": len(plan_output.get("linkedin_post_md", "")),
            "has_memory_snippet": bool(plan_output.get("memory_snippet")),
        },
        tool_output=save_output,
    )

    next_task_output = tool_decide_next_task(
        weekly_plan_md=plan_output.get("weekly_plan_md", ""),
        memory_context=memory_output.get("memory_context", ""),
    )
    record(
        step_name="decide_next_task",
        tool_name="tool_decide_next_task",
        tool_input={"weekly_plan_chars": len(plan_output.get("weekly_plan_md", ""))},
        tool_output=next_task_output,
    )

    trace_dir = base_path / "data" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    trace_path = trace_dir / f"trace_{ts}.json"
    trace_payload = [_trace_to_dict(t) for t in traces]
    trace_path.write_text(json.dumps(trace_payload, ensure_ascii=True, indent=2), encoding="utf-8")

    audit = memory_output.get("audit", {})
    return {
        "weekly_plan_path": save_output.get("weekly_plan_path"),
        "linkedin_path": save_output.get("linkedin_path"),
        "learning_unit_path": save_output.get("learning_unit_path", ""),
        "critic_report": critic_report,
        "critic_status": critic_report.get("status") if critic_report else None,
        "trace_path": trace_path.as_posix(),
        "next_task": next_task_output.get("next_task"),
        "memory_used": audit.get("memory_used", False),
        "memory_snippets_count": audit.get("memory_snippets_count", 0),
        "memory_path": save_output.get("memory_path", ""),
    }


def run_weekly_planner_agent(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int = 30,
    preferences: str | None = None,
    model: str = DEFAULT_MODEL,
    base_dir: Path | str = ".",
    enable_critic: bool = False,
) -> Dict[str, Any]:
    """Backward-compatible fixed-sequence runner."""
    return run_weekly_planner_agent_fixed(
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
        model=model,
        base_dir=base_dir,
        enable_critic=enable_critic,
    )


def build_react_controller_prompt(
    goal: str,
    hours_per_week: float,
    max_session_minutes: int,
    preferences: Dict[str, Any],
    state: Dict[str, Any],
    last_observation: str,
) -> Tuple[str, str]:
    """Build system and user prompts for the ReAct controller."""
    tools_desc = (
        "- retrieve_memory: find relevant past memory; no file paths needed.\n"
        "- load_learning_roadmap: load roadmap JSON from /roadmaps if present.\n"
        "- generate_learning_roadmap: create and save a roadmap JSON + markdown.\n"
        "- summarize_task_progress: load tasks.csv summary for planner context.\n"
        "- generate_weekly_plan: generate plan content from goal and memory.\n"
        "- upsert_tasks_from_plan: parse plan markdown and update tasks.csv.\n"
        "- save_outputs: save plan and LinkedIn draft to disk.\n"
        "- decide_next_task: pick next task from the plan."
    )
    system_prompt = (
        "You are a tool-calling controller for a weekly planning agent.\n"
        "You must respond with one JSON object only. No markdown or prose.\n"
        "Output must start with { and end with }.\n"
        "Do not wrap in ```json or any code fences.\n"
        "Allowed actions:\n"
        '{ "action": "tool", "tool_name": "...", "args": { ... } }\n'
        '{ "action": "final", "result": { ... } }\n'
        "Tool names: retrieve_memory, load_learning_roadmap, generate_learning_roadmap, "
        "summarize_task_progress, generate_weekly_plan, "
        "upsert_tasks_from_plan, save_outputs, decide_next_task.\n"
        "Decide the next tool call based on the state and last observation.\n"
        "Only call tools. Do not generate the weekly plan directly.\n"
        "POLICY (must follow this priority order):\n"
        "1) If memory_attempted == True: NEVER call retrieve_memory again in this run.\n"
        "2) If memory_attempted == False AND has_memory_context == False: call retrieve_memory ONCE.\n"
        "3) If force_regenerate_roadmap == True AND roadmap_generated == False: call generate_learning_roadmap ONCE.\n"
        "4) If roadmap_attempted == False: call load_learning_roadmap ONCE.\n"
        "5) If roadmap_exists == False AND roadmap_generated == False: call generate_learning_roadmap ONCE.\n"
        "6) If memory_hits == 0: proceed to summarize_task_progress or generate_weekly_plan; "
        "do NOT retry memory.\n"
        "7) If has_saved_paths == true AND has_next_task == true: ALWAYS return "
        '{"action":"final","result":{}}.\n'
        "8) Otherwise choose exactly ONE tool in this order:\n"
        "   a) If memory_attempted == false -> retrieve_memory\n"
        "   b) Else if force_regenerate_roadmap == true AND roadmap_generated == false -> generate_learning_roadmap\n"
        "   c) Else if roadmap_attempted == false -> load_learning_roadmap\n"
        "   d) Else if roadmap_exists == false AND roadmap_generated == false -> generate_learning_roadmap\n"
        "   e) Else if has_task_summary == false -> summarize_task_progress\n"
        "   f) Else if has_weekly_plan_md == false -> generate_weekly_plan\n"
        "   g) Else if has_tasks_upserted == false -> upsert_tasks_from_plan\n"
        "   h) Else if has_saved_paths == false -> save_outputs\n"
        "   i) Else if has_next_task == false -> decide_next_task\n"
        "   j) Else -> final\n"
        "9) Never repeat a tool if the state shows it already succeeded.\n"
        "10) Output ONLY one JSON object. No prose. No markdown.\n"
        "Example tool action: {\"action\":\"tool\",\"tool_name\":\"retrieve_memory\",\"args\":{\"k\":8}}\n"
        "Example final action: {\"action\":\"final\",\"result\":{\"weekly_plan_path\":\"...\"}}\n"
    )
    user_prompt = (
        "GOAL\n"
        f"- goal: {goal}\n"
        f"- hours_per_week: {hours_per_week}\n"
        f"- max_session_minutes: {max_session_minutes}\n"
        f"- preferences: {preferences.get('text', '')}\n\n"
        "AVAILABLE TOOLS\n"
        f"{tools_desc}\n\n"
        "STATE SUMMARY\n"
        f"- memory_used: {state.get('memory_used')}\n"
        f"- memory_snippets_count: {state.get('memory_snippets_count')}\n"
        f"- memory_attempted: {state.get('memory_attempted')}\n"
        f"- memory_hits: {state.get('memory_hits')}\n"
        f"- has_memory_context: {state.get('has_memory_context')}\n"
        f"- roadmap_attempted: {state.get('roadmap_attempted')}\n"
        f"- roadmap_exists: {state.get('roadmap_exists')}\n"
        f"- roadmap_generated: {state.get('roadmap_generated')}\n"
        f"- roadmap_generation_error: {state.get('roadmap_generation_error')}\n"
        f"- roadmap_id: {state.get('roadmap_id')}\n"
        f"- force_regenerate_roadmap: {state.get('force_regenerate_roadmap')}\n"
        f"- has_task_summary: {bool(state.get('task_progress_summary'))}\n"
        f"- has_weekly_plan_md: {bool(state.get('weekly_plan_md'))}\n"
        f"- has_tasks_upserted: {bool(state.get('tasks_upserted'))}\n"
        f"- has_saved_paths: {bool(state.get('weekly_plan_path') and state.get('linkedin_path'))}\n"
        f"- has_next_task: {bool(state.get('next_task'))}\n\n"
        f"- open_tasks_count: {state.get('open_tasks_count', 0)}\n"
        f"- needs_review_count: {state.get('needs_review_count', 0)}\n"
        f"- weak_topics: {state.get('weak_topics', [])}\n\n"
        "LAST OBSERVATION\n"
        f"{last_observation}\n\n"
        "RESPONSE FORMAT\n"
        "Return one JSON object only. Choose the next tool or finalize."
    )
    return system_prompt, user_prompt


def _parse_action(payload: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    extracted = _extract_json_object(payload)
    try:
        action = json.loads(extracted)
    except json.JSONDecodeError:
        fixed = _maybe_fix_python_dict(extracted)
        if fixed != extracted:
            try:
                action = json.loads(fixed)
            except json.JSONDecodeError as exc:
                return None, f"Invalid JSON after fix: {exc}"
        else:
            try:
                action = json.loads(extracted)
            except json.JSONDecodeError as exc:
                return None, f"Invalid JSON: {exc}"
    if not isinstance(action, dict):
        return None, "Action must be a JSON object."
    if action.get("action") == "tool":
        tool_name = action.get("tool_name")
        args = action.get("args")
        if tool_name not in TOOL_DISPATCH:
            return None, f"Invalid tool_name: {tool_name}"
        if args is None or not isinstance(args, dict):
            return None, "Tool args must be a JSON object."
        return action, None
    if action.get("action") == "final":
        result = action.get("result")
        if result is None or not isinstance(result, dict):
            return None, "Final result must be a JSON object."
        return action, None
    return None, "Action must be 'tool' or 'final'."


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
    if text.startswith("json"):
        text = text[4:].strip()
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1].strip()
    end = text.rfind("}")
    if end != -1 and end > start:
        return text[start : end + 1].strip()
    return text


def _maybe_fix_python_dict(text: str) -> str:
    if "'" not in text:
        return text
    if text.count("'") <= text.count('"'):
        return text
    if '\\"' in text or "\\'" in text:
        return text
    return text.replace("'", '"')


def _load_mock_actions(path: Path) -> List[str]:
    lines: List[str] = []
    if not path.exists():
        return lines
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _summarize_observation(tool_name: str, output: Dict[str, Any], state: Dict[str, Any]) -> str:
    if tool_name == "retrieve_memory":
        audit = output.get("audit", {})
        return f"memory_used={audit.get('memory_used')} snippets={audit.get('memory_snippets_count')}"
    if tool_name == "load_learning_roadmap":
        return f"roadmap_exists={output.get('exists')}"
    if tool_name == "generate_learning_roadmap":
        return f"roadmap_path={output.get('path')}"
    if tool_name == "summarize_task_progress":
        counts = output.get("counts_by_status", {})
        return f"open_tasks={sum(counts.values())} needs_review={counts.get('NEEDS_REVIEW', 0)}"
    if tool_name == "generate_weekly_plan":
        return f"weekly_plan_md_len={len(output.get('weekly_plan_md', ''))}"
    if tool_name == "upsert_tasks_from_plan":
        return f"created={output.get('created_count')} updated={output.get('updated_count')}"
    if tool_name == "save_outputs":
        return f"weekly_plan_path={output.get('weekly_plan_path')} linkedin_path={output.get('linkedin_path')}"
    if tool_name == "decide_next_task":
        return f"next_task={output.get('next_task')}"
    return f"state_keys={sorted(state.keys())}"


def _safe_final_result(state: Dict[str, Any], final_reason: str = "success") -> Dict[str, Any]:
    return {
        "weekly_plan_path": state.get("weekly_plan_path"),
        "linkedin_path": state.get("linkedin_path"),
        "learning_unit_path": state.get("learning_unit_path", ""),
        "next_task": state.get("next_task"),
        "memory_used": state.get("memory_used", False),
        "memory_snippets_count": state.get("memory_snippets_count", 0),
        "memory_path": state.get("memory_path", ""),
        "roadmap_path": state.get("roadmap_path", ""),
        "roadmap_exists": state.get("roadmap_exists", False),
        "roadmap_id": state.get("roadmap_id", ""),
        "roadmap_total_hours": state.get("roadmap_total_hours"),
        "roadmap_phase_count": state.get("roadmap_phase_count"),
        "roadmap_current_phase": state.get("roadmap_current_phase"),
        "roadmap_current_milestone": state.get("roadmap_current_milestone"),
        "roadmap_remaining_hours": state.get("roadmap_remaining_hours"),
        "roadmap_estimated_weeks": state.get("roadmap_estimated_weeks"),
        "roadmap_week_number": state.get("roadmap_week_number"),
        "roadmap_completed_hours": state.get("roadmap_completed_hours"),
        "roadmap_completed_milestones": state.get("roadmap_completed_milestones"),
        "roadmap_computed_week_number": state.get("roadmap_computed_week_number"),
        "roadmap_milestone_task_counts": state.get("roadmap_milestone_task_counts"),
        "roadmap_completion_mode": state.get("roadmap_completion_mode"),
        "roadmap_used_hours_per_week": state.get("roadmap_used_hours_per_week"),
        "roadmap_debug_notes": state.get("roadmap_debug_notes"),
        "critic_report": state.get("critic_report"),
        "critic_status": state.get("critic_status"),
        "final_reason": final_reason,
    }


def run_weekly_planner_agent_react(
    goal: str,
    hours_per_week: int,
    max_session_minutes: int,
    preferences: Dict[str, Any],
    model: str,
    base_dir: Path,
    max_steps: int = 10,
    mock_actions_path: Optional[Path] = None,
    enable_critic: bool = False,
) -> Dict[str, Any]:
    """Run a ReAct-style tool-calling loop and persist a trace JSON file."""
    base_path = Path(base_dir)
    max_steps = max(max_steps, 6)
    traces: List[AgentStepTrace] = []
    trace_dir = base_path / "data" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    store = LocalVectorStore(path=base_path / "data" / "memory_vectors.json")
    if mock_actions_path and mock_actions_path.suffix == ".js":
        record = AgentStepTrace(
            step_name="controller",
            tool_name="mock_path_error",
            tool_input={"mock_actions_path": mock_actions_path.as_posix()},
            tool_output_summary="invalid_mock_fixture_extension",
            tool_output_full={"error": "Mock fixtures must be JSONL (.jsonl), not .js."},
            ts=datetime.now().isoformat(),
        )
        traces.append(record)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        trace_path = trace_dir / f"trace_{ts}.json"
        trace_payload = [_trace_to_dict(t) for t in traces]
        trace_path.write_text(json.dumps(trace_payload, ensure_ascii=True, indent=2), encoding="utf-8")
        final_result = _safe_final_result({})
        final_result["trace_path"] = trace_path.as_posix()
        return final_result

    state: Dict[str, Any] = {
        "goal": goal,
        "hours_per_week": hours_per_week,
        "max_session_minutes": max_session_minutes,
        "preferences": preferences,
        "target_level": preferences.get("target_level") or "medium",
        "background": preferences.get("background") or "",
        "roadmap_id": preferences.get("roadmap_id") or "",
        "force_regenerate_roadmap": bool(preferences.get("force_regenerate_roadmap", False)),
        "memory_context": "",
        "memory_used": False,
        "memory_snippets_count": 0,
        "memory_attempted": False,
        "memory_hits": 0,
        "has_memory_context": False,
        "roadmap_attempted": False,
        "roadmap_exists": False,
        "roadmap_generated": False,
        "roadmap_generation_attempted": False,
        "roadmap_generation_error": "",
        "roadmap": None,
        "roadmap_path": "",
        "roadmap_total_hours": None,
        "roadmap_phase_count": None,
        "roadmap_current_phase": None,
        "roadmap_current_milestone": None,
        "roadmap_remaining_hours": None,
        "roadmap_week_number": None,
        "roadmap_completed_hours": None,
        "roadmap_completed_milestones": None,
        "roadmap_computed_week_number": None,
        "roadmap_milestone_task_counts": None,
        "roadmap_completion_mode": None,
        "roadmap_used_hours_per_week": None,
        "roadmap_debug_notes": None,
        "weekly_plan_md": "",
        "linkedin_post_md": "",
        "learning_unit_md": "",
        "memory_snippet": "",
        "weekly_plan_path": "",
        "linkedin_path": "",
        "learning_unit_path": "",
        "memory_path": "",
        "next_task": "",
        "tasks_path": (base_path / "data" / "tasks.csv").as_posix(),
        "task_progress_summary": {},
        "tasks_upserted": False,
        "open_tasks_count": 0,
        "needs_review_count": 0,
        "weak_topics": [],
        "enable_critic": enable_critic,
        "critic_attempted": False,
        "critic_report": None,
        "critic_status": None,
    }

    def _next_required_tool(run_state: Dict[str, Any]) -> Optional[str]:
        if not run_state.get("memory_attempted"):
            return "retrieve_memory"
        if run_state.get("force_regenerate_roadmap") and not run_state.get("roadmap_generation_attempted"):
            return "generate_learning_roadmap"
        if not run_state.get("roadmap_attempted"):
            return "load_learning_roadmap"
        if not run_state.get("roadmap_exists") and not run_state.get("roadmap_generation_attempted"):
            return "generate_learning_roadmap"
        if not run_state.get("task_progress_summary"):
            return "summarize_task_progress"
        if not run_state.get("weekly_plan_md"):
            return "generate_weekly_plan"
        if not run_state.get("tasks_upserted"):
            return "upsert_tasks_from_plan"
        if not (
            run_state.get("weekly_plan_path")
            and run_state.get("linkedin_path")
            and run_state.get("learning_unit_path")
        ):
            return "save_outputs"
        if not run_state.get("next_task"):
            return "decide_next_task"
        return None
    last_observation = "No previous tool calls."
    final_reason = "success"

    mock_actions: List[str] = _load_mock_actions(mock_actions_path) if mock_actions_path else []
    mock_index = 0
    last_tool_name = ""
    same_tool_count = 0

    def record(step_name: str, tool_name: str, tool_input: Dict[str, Any], tool_output: Dict[str, Any]) -> None:
        traces.append(
            AgentStepTrace(
                step_name=step_name,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output_summary=_summarize_output(step_name, tool_output),
                tool_output_full=tool_output,
                ts=datetime.now().isoformat(),
            )
        )

    # Termination is decided by the controller policy, not the loop.
    finished = False
    for _ in range(max_steps):
        if same_tool_count >= 3:
            if last_tool_name == "retrieve_memory" and state.get("memory_hits", 0) == 0:
                same_tool_count = 0
                last_tool_name = ""
            else:
                final_reason = "exception"
                record(
                    step_name="controller",
                    tool_name="safety_stop",
                    tool_input={"reason": "same_tool_three_times"},
                    tool_output={"action": "final", "result": _safe_final_result(state, final_reason)},
                )
                finished = True
                break

        system_prompt, user_prompt = build_react_controller_prompt(
            goal=goal,
            hours_per_week=hours_per_week,
            max_session_minutes=max_session_minutes,
            preferences=preferences,
            state=state,
            last_observation=last_observation,
        )

        raw_action = ""
        action = None
        error = None
        retries = 0
        while retries < 2 and action is None:
            if mock_actions:
                if mock_index >= len(mock_actions):
                    error = "Mock actions exhausted."
                    break
                raw_action = mock_actions[mock_index]
                mock_index += 1
            else:
                raw_action = call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=0.0,
                )

            extracted = _extract_json_object(raw_action)
            action, error = _parse_action(raw_action)
            if action is None and retries == 0:
                record(
                    step_name="controller",
                    tool_name="format_error",
                    tool_input={
                        "raw_response_excerpt": raw_action[:300],
                        "extracted_json": extracted,
                        "error": error,
                    },
                    tool_output={"action": "invalid"},
                )
                if not mock_actions:
                    system_prompt = (
                        "Return ONLY valid JSON matching the schema. No markdown or prose."
                    )
                    user_prompt = (
                        "Schema: {\"action\":\"tool\",\"tool_name\":\"...\",\"args\":{...}} or "
                        "{\"action\":\"final\",\"result\":{...}}.\n"
                        f"Invalid response error: {error}\nReturn a valid JSON object now."
                    )
            retries += 1

        if action is None:
            record(
                step_name="controller",
                tool_name="parse_error",
                tool_input={"raw_response": raw_action, "error": error},
                tool_output={"action": "invalid"},
            )
            if not state.get("weekly_plan_md"):
                action = {"action": "tool", "tool_name": "generate_weekly_plan", "args": {}}
            else:
                final_reason = "parse_error"
                record(
                    step_name="controller",
                    tool_name="safety_stop",
                    tool_input={"reason": "parse_error"},
                    tool_output={"action": "final", "result": _safe_final_result(state, final_reason)},
                )
                finished = True
                break

        override_reason = ""
        if action.get("action") == "final" and not state.get("weekly_plan_md"):
            action = {"action": "tool", "tool_name": "generate_weekly_plan", "args": {}}
            override_reason = "final_before_plan"
        if (
            action.get("action") == "tool"
            and action.get("tool_name") == "load_learning_roadmap"
            and state.get("force_regenerate_roadmap")
            and not state.get("roadmap_generated")
        ):
            action = {"action": "tool", "tool_name": "generate_learning_roadmap", "args": {}}
            override_reason = "roadmap_force_regenerate_override_load"
        if (
            action.get("action") == "tool"
            and action.get("tool_name") == "retrieve_memory"
            and state.get("memory_attempted")
        ):
            next_tool = "summarize_task_progress"
            if state.get("task_progress_summary"):
                next_tool = "generate_weekly_plan"
            action = {"action": "tool", "tool_name": next_tool, "args": {}}
            override_reason = "memory_no_hits" if state.get("memory_hits", 0) == 0 else "memory_already_attempted"
        if (
            action.get("action") == "tool"
            and action.get("tool_name") == "generate_weekly_plan"
            and state.get("force_regenerate_roadmap")
            and not state.get("roadmap_generated")
        ):
            action = {"action": "tool", "tool_name": "generate_learning_roadmap", "args": {}}
            override_reason = "roadmap_force_regenerate_before_plan"
        if (
            action.get("action") == "tool"
            and action.get("tool_name") == "generate_weekly_plan"
            and not state.get("roadmap_attempted")
        ):
            action = {"action": "tool", "tool_name": "load_learning_roadmap", "args": {}}
            override_reason = "roadmap_load_before_plan"
        if (
            action.get("action") == "tool"
            and action.get("tool_name") == "generate_weekly_plan"
            and state.get("roadmap_attempted")
            and not state.get("roadmap_exists")
            and not state.get("roadmap_generated")
        ):
            action = {"action": "tool", "tool_name": "generate_learning_roadmap", "args": {}}
            override_reason = "roadmap_generate_before_plan"

        if (
            action.get("action") == "tool"
            and action.get("tool_name") == "generate_learning_roadmap"
            and state.get("roadmap_generation_attempted")
        ):
            # Guard against repeated roadmap generation attempts within one run.
            if not state.get("task_progress_summary"):
                action = {"action": "tool", "tool_name": "summarize_task_progress", "args": {}}
            else:
                action = {"action": "tool", "tool_name": "generate_weekly_plan", "args": {}}
            override_reason = "roadmap_already_attempted"

        required_tool = _next_required_tool(state)
        if required_tool and (
            action.get("action") != "tool" or action.get("tool_name") != required_tool
        ):
            # Pipeline guardrail: enforce the next required tool to ensure forward progress.
            action = {"action": "tool", "tool_name": required_tool, "args": {}}
            override_reason = "pipeline_required_tool"

        record(
            step_name="controller",
            tool_name="controller",
            tool_input={
                "prompt_state": _summarize_observation("controller", {}, state),
                "memory_attempted": state.get("memory_attempted"),
                "memory_hits": state.get("memory_hits"),
            },
            tool_output={
                "action": action,
                "chosen_tool": action.get("tool_name") if action.get("action") == "tool" else "final",
                "controller_raw": raw_action,
                "parse_error": error,
                "override": bool(override_reason),
                "override_reason": override_reason or None,
            },
        )

        if action.get("action") == "final":
            result = action.get("result", {})
            final_reason = "success"
            final = _safe_final_result(state, final_reason)
            final.update({k: v for k, v in result.items() if v})
            state.update(final)
            finished = True
            break

        tool_name = action.get("tool_name")
        args = action.get("args", {})
        if tool_name == last_tool_name:
            same_tool_count += 1
        else:
            same_tool_count = 1
            last_tool_name = tool_name

        if tool_name == "retrieve_memory":
            k = int(args.get("k", 8))
            output = tool_retrieve_memory(goal=goal, preferences=preferences, store=store, k=k)
            state["memory_context"] = output.get("memory_context", "")
            audit = output.get("audit", {})
            state["memory_used"] = audit.get("memory_used", False)
            state["memory_snippets_count"] = audit.get("memory_snippets_count", 0)
            state["memory_attempted"] = True
            state["memory_hits"] = int(audit.get("memory_snippets_count", 0))
            state["has_memory_context"] = bool(state.get("memory_context"))
        elif tool_name == "load_learning_roadmap":
            output = tool_load_learning_roadmap(
                goal=goal,
                base_dir=base_path,
                roadmap_id=state.get("roadmap_id") or None,
                force_regenerate=state.get("force_regenerate_roadmap", False),
            )
            state["roadmap_attempted"] = True
            state["roadmap_exists"] = bool(output.get("exists") and output.get("roadmap"))
            state["roadmap"] = output.get("roadmap")
            state["roadmap_path"] = output.get("path", "")
        elif tool_name == "generate_learning_roadmap":
            output = tool_generate_learning_roadmap(
                goal=goal,
                target_level=state.get("target_level", "medium"),
                background=state.get("background"),
                roadmap_id=state.get("roadmap_id") or None,
                base_dir=base_path,
                model=model,
            )
            state["roadmap_attempted"] = True
            state["roadmap_generation_attempted"] = True
            if output.get("error"):
                state["roadmap_generation_error"] = output.get("error", "")
                state["roadmap_generated"] = False
                state["roadmap"] = None
                state["roadmap_exists"] = False
                state["roadmap_path"] = output.get("path", "")
            else:
                state["roadmap_generation_error"] = ""
                state["roadmap_generated"] = True
                state["roadmap"] = output.get("roadmap")
                state["roadmap_exists"] = bool(state.get("roadmap"))
                state["roadmap_path"] = output.get("path", "")
                if output.get("roadmap_id"):
                    state["roadmap_id"] = output.get("roadmap_id")
        elif tool_name == "summarize_task_progress":
            tasks_path = Path(state.get("tasks_path"))
            output = tool_summarize_task_progress(tasks_path=tasks_path)
            state["task_progress_summary"] = output
            counts = output.get("counts_by_status", {})
            open_count = sum(counts.get(status, 0) for status in ("TODO", "IN_PROGRESS", "NEEDS_REVIEW"))
            state["open_tasks_count"] = open_count
            state["needs_review_count"] = counts.get("NEEDS_REVIEW", 0)
            state["weak_topics"] = output.get("weak_topics", [])
        elif tool_name == "generate_weekly_plan":
            output = tool_generate_weekly_plan(
                goal=goal,
                hours_per_week=hours_per_week,
                max_session_minutes=max_session_minutes,
                preferences=preferences,
                memory_context=state.get("memory_context", ""),
                audit={
                    "memory_used": state.get("memory_used", False),
                    "memory_snippets_count": state.get("memory_snippets_count", 0),
                },
                model=model,
                base_dir=base_path,
                task_progress=state.get("task_progress_summary"),
                roadmap=state.get("roadmap"),
                roadmap_path=state.get("roadmap_path"),
                roadmap_id=state.get("roadmap_id") or None,
            )
            state["weekly_plan_md"] = output.get("weekly_plan_md", "")
            state["linkedin_post_md"] = output.get("linkedin_post_md", "")
            state["learning_unit_md"] = output.get("learning_unit_md", "")
            state["memory_snippet"] = output.get("memory_snippet", "")
            roadmap_meta = output.get("roadmap_meta") or {}
            if roadmap_meta:
                state["roadmap_id"] = roadmap_meta.get("roadmap_id") or state.get("roadmap_id")
                state["roadmap_total_hours"] = roadmap_meta.get("total_estimated_hours")
                state["roadmap_estimated_weeks"] = roadmap_meta.get("estimated_weeks_at_hours_per_week")
                state["roadmap_phase_count"] = roadmap_meta.get("phase_count")
                state["roadmap_current_phase"] = roadmap_meta.get("current_phase")
                state["roadmap_current_milestone"] = roadmap_meta.get("current_milestone")
                state["roadmap_remaining_hours"] = roadmap_meta.get("remaining_hours")
                state["roadmap_week_number"] = roadmap_meta.get("week_number")
                state["roadmap_completed_hours"] = roadmap_meta.get("completed_hours")
                state["roadmap_completed_milestones"] = roadmap_meta.get("completed_milestones")
                state["roadmap_computed_week_number"] = roadmap_meta.get("computed_week_number")
                state["roadmap_milestone_task_counts"] = roadmap_meta.get("milestone_task_counts")
                state["roadmap_completion_mode"] = roadmap_meta.get("milestone_completion_mode")
                state["roadmap_used_hours_per_week"] = roadmap_meta.get("used_hours_per_week")
                state["roadmap_debug_notes"] = roadmap_meta.get("debug_notes")
            state["tasks_upserted"] = False
            if state.get("enable_critic") and not state.get("critic_attempted"):
                misbehaviors_path = base_path / "docs" / "misbehaviors.md"
                misbehaviors_chars = (
                    len(misbehaviors_path.read_text(encoding="utf-8"))
                    if misbehaviors_path.exists()
                    else 0
                )
                critic_report = run_plan_critic(
                    weekly_plan_md=state.get("weekly_plan_md", ""),
                    base_dir=base_path,
                    model=model,
                )
                state["critic_attempted"] = True
                state["critic_report"] = critic_report
                state["critic_status"] = critic_report.get("status")
                record(
                    step_name="critic_plan_review",
                    tool_name="tool_critic_plan_review",
                    tool_input={
                        "plan_chars": len(state.get("weekly_plan_md", "")),
                        "misbehaviors_chars": misbehaviors_chars,
                    },
                    tool_output=critic_report,
                )
        elif tool_name == "upsert_tasks_from_plan":
            output = tool_upsert_tasks_from_plan(
                plan_md=state.get("weekly_plan_md", ""),
                tasks_path=Path(state.get("tasks_path")),
                source_week=date.today().isoformat(),
                default_priority=3,
                roadmap_id=state.get("roadmap_id") or None,
            )
            state["tasks_upserted"] = True
        elif tool_name == "save_outputs":
            output = tool_save_outputs(
                base_dir=base_path,
                weekly_plan_md=state.get("weekly_plan_md", ""),
                linkedin_post_md=state.get("linkedin_post_md", ""),
                memory_snippet=state.get("memory_snippet", ""),
                learning_unit_md=state.get("learning_unit_md", ""),
                learning_unit_slug_source=state.get("goal") or "",
            )
            state["weekly_plan_path"] = output.get("weekly_plan_path", "")
            state["linkedin_path"] = output.get("linkedin_path", "")
            state["memory_path"] = output.get("memory_path", "")
            state["learning_unit_path"] = output.get("learning_unit_path", "")
            learning_progress_path = resolve_learning_progress_path(base_path)
            _progress, progress_week = append_week_from_plan(
                path=learning_progress_path,
                plan_md=state.get("weekly_plan_md", ""),
                roadmap_id=state.get("roadmap_id") or "",
                phase_id=state.get("roadmap_current_phase") or "",
                milestone_id=state.get("roadmap_current_milestone") or "",
                week_number_global=state.get("roadmap_week_number"),
                goal=state.get("goal") or goal,
            )
            state["learning_progress_path"] = learning_progress_path.as_posix()
            state["learning_progress_week_id"] = progress_week.get("week_id", "")
        elif tool_name == "decide_next_task":
            output = tool_decide_next_task(
                weekly_plan_md=state.get("weekly_plan_md", ""),
                memory_context=state.get("memory_context", ""),
            )
            state["next_task"] = output.get("next_task", "")
        else:
            output = {"error": f"Unknown tool: {tool_name}"}

        record(
            step_name=tool_name,
            tool_name=f"tool_{tool_name}",
            tool_input=args,
            tool_output=output,
        )
        last_observation = _summarize_observation(tool_name, output, state)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    trace_path = trace_dir / f"trace_{ts}.json"
    trace_payload = [_trace_to_dict(t) for t in traces]
    trace_path.write_text(json.dumps(trace_payload, ensure_ascii=True, indent=2), encoding="utf-8")

    if not finished:
        final_reason = "max_steps"
    final_result = _safe_final_result(state, final_reason)
    final_result["trace_path"] = trace_path.as_posix()
    return final_result
