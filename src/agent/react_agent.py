"""Minimal ReAct-style agent runner for weekly planning."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory.vector_store import LocalVectorStore
from .tools import (
    tool_decide_next_task,
    tool_generate_weekly_plan,
    tool_retrieve_memory,
    tool_save_outputs,
)
from .weekly_planner import DEFAULT_MODEL, call_llm

TOOL_DISPATCH = {
    "retrieve_memory": tool_retrieve_memory,
    "generate_weekly_plan": tool_generate_weekly_plan,
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
    if step_name in {"generate_plan", "generate_weekly_plan", "tool_generate_weekly_plan"}:
        plan_len = len(output.get("weekly_plan_md", ""))
        return f"generated plan chars={plan_len}"
    if step_name in {"save_outputs", "tool_save_outputs"}:
        return f"saved plan={output.get('weekly_plan_path')} linkedin={output.get('linkedin_path')}"
    if step_name in {"decide_next_task", "tool_decide_next_task"}:
        return f"next_task={output.get('next_task')}"
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
    memory_output = tool_retrieve_memory(goal=goal, preferences=preferences_payload, store=store, k=8)
    record(
        step_name="retrieve_memory",
        tool_name="tool_retrieve_memory",
        tool_input={"goal": goal, "preferences": preferences_payload, "k": 8},
        tool_output=memory_output,
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

    save_output = tool_save_outputs(
        base_dir=base_path,
        weekly_plan_md=plan_output.get("weekly_plan_md", ""),
        linkedin_post_md=plan_output.get("linkedin_post_md", ""),
        memory_snippet=plan_output.get("memory_snippet", ""),
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
) -> Dict[str, Any]:
    """Backward-compatible fixed-sequence runner."""
    return run_weekly_planner_agent_fixed(
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
        model=model,
        base_dir=base_dir,
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
        "- generate_weekly_plan: generate plan content from goal and memory.\n"
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
        "Tool names: retrieve_memory, generate_weekly_plan, save_outputs, decide_next_task.\n"
        "Decide the next tool call based on the state and last observation.\n"
        "Only call tools. Do not generate the weekly plan directly.\n"
        "POLICY (must follow this priority order):\n"
        "1) If has_saved_paths == true AND has_next_task == true: ALWAYS return "
        '{"action":"final","result":{}}.\n'
        "2) Otherwise choose exactly ONE tool in this order:\n"
        "   a) If has_memory_context == false -> retrieve_memory\n"
        "   b) Else if has_weekly_plan_md == false -> generate_weekly_plan\n"
        "   c) Else if has_saved_paths == false -> save_outputs\n"
        "   d) Else if has_next_task == false -> decide_next_task\n"
        "   e) Else -> final\n"
        "3) Never repeat a tool if the state shows it already succeeded.\n"
        "4) Output ONLY one JSON object. No prose. No markdown.\n"
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
        f"- has_memory_context: {bool(state.get('memory_context'))}\n"
        f"- has_weekly_plan_md: {bool(state.get('weekly_plan_md'))}\n"
        f"- has_saved_paths: {bool(state.get('weekly_plan_path') and state.get('linkedin_path'))}\n"
        f"- has_next_task: {bool(state.get('next_task'))}\n\n"
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
    if tool_name == "generate_weekly_plan":
        return f"weekly_plan_md_len={len(output.get('weekly_plan_md', ''))}"
    if tool_name == "save_outputs":
        return f"weekly_plan_path={output.get('weekly_plan_path')} linkedin_path={output.get('linkedin_path')}"
    if tool_name == "decide_next_task":
        return f"next_task={output.get('next_task')}"
    return f"state_keys={sorted(state.keys())}"


def _safe_final_result(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "weekly_plan_path": state.get("weekly_plan_path"),
        "linkedin_path": state.get("linkedin_path"),
        "next_task": state.get("next_task"),
        "memory_used": state.get("memory_used", False),
        "memory_snippets_count": state.get("memory_snippets_count", 0),
        "memory_path": state.get("memory_path", ""),
    }


def run_weekly_planner_agent_react(
    goal: str,
    hours_per_week: int,
    max_session_minutes: int,
    preferences: Dict[str, Any],
    model: str,
    base_dir: Path,
    max_steps: int = 8,
    mock_actions_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run a ReAct-style tool-calling loop and persist a trace JSON file."""
    base_path = Path(base_dir)
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
        "memory_context": "",
        "memory_used": False,
        "memory_snippets_count": 0,
        "weekly_plan_md": "",
        "linkedin_post_md": "",
        "memory_snippet": "",
        "weekly_plan_path": "",
        "linkedin_path": "",
        "memory_path": "",
        "next_task": "",
    }
    last_observation = "No previous tool calls."

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
    for _ in range(max_steps):
        if same_tool_count >= 3:
            record(
                step_name="controller",
                tool_name="safety_stop",
                tool_input={"reason": "same_tool_three_times"},
                tool_output={"action": "final", "result": _safe_final_result(state)},
            )
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
                        "You must return one valid JSON object only. No markdown or prose. Fix the response."
                    )
                    user_prompt = f"Invalid response error: {error}\nReturn a valid JSON object now."
            retries += 1

        if action is None:
            record(
                step_name="controller",
                tool_name="format_failure",
                tool_input={"raw_response": raw_action, "error": error},
                tool_output={"action": "final", "result": _safe_final_result(state)},
            )
            break

        record(
            step_name="controller",
            tool_name="controller",
            tool_input={"prompt_state": _summarize_observation("controller", {}, state)},
            tool_output={"action": action},
        )

        if action.get("action") == "final":
            result = action.get("result", {})
            final = _safe_final_result(state)
            final.update({k: v for k, v in result.items() if v})
            state.update(final)
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
            )
            state["weekly_plan_md"] = output.get("weekly_plan_md", "")
            state["linkedin_post_md"] = output.get("linkedin_post_md", "")
            state["memory_snippet"] = output.get("memory_snippet", "")
        elif tool_name == "save_outputs":
            output = tool_save_outputs(
                base_dir=base_path,
                weekly_plan_md=state.get("weekly_plan_md", ""),
                linkedin_post_md=state.get("linkedin_post_md", ""),
                memory_snippet=state.get("memory_snippet", ""),
            )
            state["weekly_plan_path"] = output.get("weekly_plan_path", "")
            state["linkedin_path"] = output.get("linkedin_path", "")
            state["memory_path"] = output.get("memory_path", "")
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

    final_result = _safe_final_result(state)
    final_result["trace_path"] = trace_path.as_posix()
    return final_result
